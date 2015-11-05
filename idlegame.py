from flask import Flask, session, request, jsonify, render_template, make_response

import re
import json
import os
from itertools import chain
from collections import OrderedDict, Counter, namedtuple
from threading import Thread
from time import sleep
from random import randrange

app = Flask(__name__)

app.debug = True

SPEEDUP = 10


class Resource:
    all_ = OrderedDict()

    def __init__(self, name, parent=None):
        self.parent = parent
        self.idstring = name
        self.rawname = name.split("->")[0]
        try:
            if "->" in name:
                if "#" in name:
                    self.imagepath, self.color = name.split("->")[1].split("#")
                    if not self.imagepath:
                        self.imagepath = parent.imagepath
                else:
                    self.imagepath = name.split("->")[1]
                    self.color = parent.color
            else:
                self.imagepath, self.color = parent.imagepath, parent.color
        except AttributeError:
            self.imagepath, self.color = "moebius-star", "f00"
        with open("static/icons/" + self.imagepath + ".svg") as file:
            self.image = file.read()
            self.image = self.image.replace("\"#fff\"", "\"#{}\"".format(self.color)) \
                .replace("\"#000\"", "\"#fff\"")
        if "*" in self.rawname:
            showname, subname = self.rawname.split("*")
        elif "@" in self.rawname:
            showname = self.rawname
            subname = self.rawname.replace("@", "").strip()
        else:
            showname = "@"
            subname = self.rawname

        self.childfill = showname.replace("@", "{}")
        if self.parent is None:
            self.displayname = subname
            self.pathname = subname
        else:
            self.displayname = self.parent.childfill.format(subname)
            self.pathname = self.parent.pathname + "/" + subname
        self.image = "<span title=\"{}\">{}</span>".format(self.displayname, self.image)

        p = self
        self.level = -1
        while p is not None:
            p = p.parent
            self.level += 1

        Resource.all_[self.pathname] = self
        update.auto("/get_resourse/{}/".format(self.js_id), "res_" + self.js_id)
        update.auto("/get_resourse_gain/{}/".format(self.js_id), "resg_" + self.js_id)

    @property
    def get_children(self):
        for v in list(Resource.all_.values()):  # list to prevent RuntimeError: dictionary changed size during iteration
            if v.parent == self:
                yield v

    def show(self, index=0):
        # yield ">" + "    "*index + self.pathname + "    ( " + self.displayname + " )"
        yield js_resourse(self)
        for r in self.get_children:
            for s in r.show(index + 1):
                yield s

    @staticmethod
    def show_all():
        for k, v in Resource.all_.items():
            if v.parent is None:
                for s in v.show():
                    yield s

    @staticmethod
    def get_by_path(path):
        return Resource.all_[path]

    @staticmethod
    def get_by_id(id_):
        for s in Resource.all_.values():
            if s.js_id == id_:
                return s
        assert True, "Invalid Id"  # Should not get here

    @staticmethod
    def load():
        print(os.getcwd())
        with open("resources.json") as file:
            data = json.load(file, object_pairs_hook=OrderedDict)  # Ordered dict to force load order
            for k, v in data.items():
                Resource(k).unpack(v)

    def unpack(self, data):
        for k, v in data.items():
            if k.startswith("+"):
                for i in Resource.get_by_path(k[1:]).get_children:
                    Resource(i.idstring, self)
            else:
                Resource(k, self).unpack(v)

    @property
    def js_id(self):
        return self.pathname.replace("/", "_").replace(" ", "_")

    @property
    def pure(self):
        return any(True for _ in self.get_children)


def js_resourse(resource):
    jump = "&nbsp;&nbsp;&nbsp;&nbsp;" * resource.level
    if resource.pure:
        name = "<a href=\"javascript:hide_{js_id}()\" id=\"button_{js_id}\">{name}</a>" \
            .format(name=resource.displayname, js_id=resource.js_id)
        show_funcs = "\n".join(
            """
            document.getElementById("row_{}").style.display = "";

            """.format(r.js_id) for r in resource.get_children)

        hide_funcs = "\n".join(
            """
            document.getElementById("row_{}").style.display = "none";

            """.format(r.js_id) for r in resource.get_children)
        autohide = "hide_{}();".format(resource.js_id)
    else:
        name = resource.displayname
        show_funcs = ""
        hide_funcs = ""
        autohide = ""
    return """

    <tr id="row_{js_id}"">
        <td>
            {jump}{image}{name}
        </td>
        <td>
            <div id="res_{js_id}">Invalid</div>
        </td>
        <td>
            <div id="resg_{js_id}">Invalid</div>
        </td>

    <script>
        function show_{js_id}()
        {{
            {show}
            document.getElementById("button_{js_id}").setAttribute("href","javascript:hide_{js_id}()")

        }}
        function hide_{js_id}()
        {{
            {hide}
            document.getElementById("button_{js_id}").setAttribute("href","javascript:show_{js_id}()")

        }}

        function load_{js_id}(){{
        {autohide}
        }}
        $(document).ready(load_{js_id});
    </script>
    </tr>


    """.format(jump=jump, image=resource.image, name=name, js_id=resource.js_id,
               show=show_funcs, hide=hide_funcs, autohide=autohide)


ClientValue = namedtuple("ClientValue", "html_id,url,update_type")


class Updater:  # handles server-side of AJAX
    def __init__(self):
        self.clientValues = []

    def auto(self, url, html_id):
        self.clientValues.append(ClientValue(html_id, url, "auto"))

    def change(self, url, html_id):
        self.clientValues.append(ClientValue(html_id, url, "change"))

    def makeRequestCode(self):
        for i in self.clientValues:
            yield """""".format(id=i.html_id, html=i.html_id)

    def make_urls(self):
        for i in self.clientValues:
            yield """
            document.getElementById("{id}").innerHTML=data.{id};
            """.format(id=i.html_id)

    def link(self, url):
        id_ = url.replace("/", "_")
        return "javascript:FollowUrl('{}')".format(url)

    def get_html(self):

        return """
            var xmlhttp;
            if (window.XMLHttpRequest)
              {{// code for IE7+, Firefox, Chrome, Opera, Safari
              xmlhttp=new XMLHttpRequest();
              }}
            else
              {{// code for IE6, IE5
              xmlhttp=new ActiveXObject("Microsoft.XMLHTTP");
              }}
            xmlhttp.onreadystatechange=function()
              {{
                if (xmlhttp.readyState==4 && xmlhttp.status==200)
                {{
                var data = JSON.parse(xmlhttp.responseText)
                {}
                }}
              }}
            function loadXMLDoc()
            {{
                xmlhttp.open("GET","/get/data/",true);
                xmlhttp.send();
            }}
            function load(){{
            var t=setInterval(loadXMLDoc,5000);
            loadXMLDoc();
            }}
            $(document).ready(load);
            function followUrl(url)
            {{
                window.location = url;
                setTimeout(function() {{ loadXMLDoc(); }}, 300);
            }}
            """.format("\n".join(self.make_urls()))


class Player:
    all_ = {}

    def __init__(self, id_):
        self.id_ = id_
        self.resources = Counter()
        self.resourcesPrev = self.resources.copy()
        self.resourcesGain = self.resources.copy()
        self.plots = []
        Backclock(self).start()
        Player.all_[self.id_] = self

    @classmethod
    def get(cls):
        id_ = request.cookies.get("player_id", hex(randrange(16 ** 16)))
        if id_ in cls.all_:
            return cls.all_[id_]
        else:
            return cls(id_)

    def get_resource(self, resource):
        return self.resources[resource.pathname] + sum(self.get_resource(r) for r in resource.get_children)

    def get_resource_gain(self, resource):
        return self.resourcesGain[resource.pathname] + sum(self.get_resource_gain(r) for r in resource.get_children)

    def pay(self, mats, speedup=True):

        if all(self.resources[mat.path] >= mat.amount*(SPEEDUP if speedup else 1) for mat in mats):
            self.resources -= {mat.path: mat.amount*(SPEEDUP if speedup else 1) for mat in mats}
            return True
        return False

    def gain(self, mats, speedup=True):
        self.resources += {mat.path: mat.amount*(SPEEDUP if speedup else 1) for mat in mats}

    def step(self):
        self.resourcesGain = self.resources - self.resourcesPrev
        self.resourcesPrev = self.resources.copy()
        left = 1000 * max(len(self.plots)-4,0) ** 2
        if self.get_resource(Resource.get_by_path("food")) >= left:
            for i in Resource.all_:
                if i.startswith("food") and self.resources[i]:
                    am = min(left, self.resources[i])
                    self.resources[i] -= am
                    left -= am
            Plot(self)
        for i in self.plots:
            i.step(self)


class Backclock(Thread):
    def __init__(self, player):
        Thread.__init__(self)
        self.player = player

    def run(self):
        while 1:
            sleep(2)

            self.player.step()
            print("updated" + self.player.id_)


Material = namedtuple("Material", "path,amount")


def unittimes(unit):
    a, b = unit.split(":")
    return Material(a, int(b))


def display(mat):
    if not mat.amount:
        return ""
    return "{} x{}".format(Resource.get_by_path(mat.path).image, mat.amount)


class Reaction:
    def __init__(self, start, ends):
        self.starts = list(map(unittimes, start))
        self.ends = map(unittimes, ends)

    def get_creation(self, ingr):
        assert ingr.startswith(self.starts[0].path)
        for e in self.ends:
            path, amount = e
            # example: start=metal/ore, end=metal/bar ingr=metal/ore/copper -> product=metal/bar + /copper
            product = path + ingr[len(self.starts[0].path):]
            while product not in Resource.all_:
                product = "/".join(product.split("/")[:-1])
            yield Material(product, amount)

    def get_raws(self):
        for i in Resource.all_.values():
            if self.starts and i.pathname.startswith(self.starts[0].path):
                yield Reaction_Raw([Material(i.pathname, self.starts[0].amount)] + self.starts[1:], list(self.get_creation(i.pathname)))


Reaction_Raw = namedtuple("RawReaction", "startlist,endlist")


class Workshop:
    all_ = []

    def __init__(self, jsondict):
        self.reactions = []
        for i in jsondict["reactions"]:
            if "->" not in i:
                start = []
                ends = [x.strip() for x in i.split("+")]
            else:
                start = [x.strip() for x in i.split("->")[0].split("+")]
                ends = [x.strip() for x in i.split("->")[1].split("+")]
            self.reactions.extend(Reaction(start, ends).get_raws())
        self.cost = list(map(unittimes, jsondict["cost"]))
        self.name = jsondict["name"]
        self.parentname = jsondict.get("parent", None)
        Workshop.all_.append(self)

    def step(self, active, player):
        if self.reactions:
            #print(self.reactions)
            r = self.reactions[active % len(self.reactions)]
            if player.pay(r.startlist):
                player.gain(r.endlist)

    def get_string_active(self, index):
        r = self.reactions[index % len(self.reactions)]
        return " + ".join(map(display, r.startlist)) + " -> " + " + ".join(map(display, r.endlist))

    def get_children(self):
        for i in Workshop.all_:
            if i.parentname == self.name:
                yield i

    @property
    def display(self):
        return self.name + "  (" + " ".join(display(m) for m in self.cost) + ")"

    @staticmethod
    def load():
        with open("workshops.json") as file:
            data = json.load(file, object_pairs_hook=OrderedDict)  # Ordered dict to force load order
            for d in data:
                Workshop(d)


class Plot:
    all_ = {}

    def __init__(self, player):
        self.id_ = hex(randrange(16 ** 16))
        self.player = player
        player.plots.append(self)
        self.workshop = forest
        self.build = 0
        self.active = 0
        Plot.all_[self.id_] = self

    def step(self, player):
        if self.build > 0:
            if player.pay(self.workshop.cost,False):
                self.build -= 1
        else:
            self.workshop.step(self.active, player)

    def get_active(self):
        if self.build > 0:
            return "under construction " + str(self.build) + "x" + ",".join(display(i) for i in self.workshop.cost) + " left"
        else:
            return self.workshop.get_string_active(self.active)

    def get_inactive(self,index):
        try:
            return self.workshop.get_string_active(index)
        except IndexError:
            return ""

    def change_workshop(self, new):
        self.workshop = new
        self.build = 10

    @staticmethod  # static because None must be an option if it doesn't exist
    def show_plot(index):
        return """
                <table>
                    <col width="200">
                    <col width="300">
                    <tr>
                        <td>
                            <div id="plot_reaction_{index}">plot reaction</div>
                        </td>
                        <td>
                        </td>
                    </tr>
                    <tr>
                        <td>
                            produce
                        </td>
                        <td>
                            upgrade
                        </td>
                    </tr>
                    <tr>
                        <td>
                            <a href="('/workshop/set/0/{index}')" id="reaction_0_{index}">Invalid</a>
                        </td>
                        <td>
                            <a href="('/workshop/upgrade/0/{index}')" id="upgrade_0_{index}">upgrade 0<div></a>
                        </td>
                    </tr>
                    <tr>
                        <td>
                            <a href="('/workshop/set/1/{index}')" id="reaction_1_{index}">Invalid</a>
                        </td>
                        <td>
                            <a href="('/workshop/upgrade/1/{index}')" id="upgrade_1_{index}">upgrade 1<div></a>

                        </td>
                    </tr>
                    <tr>
                        <td>
                            <a href="('/workshop/set/2/{index}')" id="reaction_2_{index}">Invalid</a>
                        </td>
                        <td>
                            <a href="('/workshop/upgrade/2/{index}')" id="upgrade_2_{index}">upgrade 2<div></a>

                        </td>
                    </tr>
                </table>
        <script>
            function load_plot_{index}(){{
            var t=setInterval(plot_update_{index},5000);
            plot_update_{index}();
            }}
            $(document).ready(load_plot_{index});
            function plot_update_{index}()
            {{
            if (document.getElementById("plot_name_{index}").innerHTML != "")
            {{
                document.getElementById("plot_name_{index}").style.display = "";
            }}
            else
            {{
                document.getElementById("plot_name_{index}").style.display = "none";
            }}
            }}
        </script>
        """.format(index=index).replace("\"('", "\"javascript:followUrl('")


def init_plots():
    for index in range(200):
        update.auto("/workshop/get/name/{}/".format(index), "plot_name_{}".format(index))
        update.auto("/workshop/get/reaction/{}/".format(index), "plot_reaction_{}".format(index))
        update.auto("/workshop/get/0/{}/".format(index), "upgrade_0_{}".format(index))
        update.auto("/workshop/get/1/{}/".format(index), "upgrade_1_{}".format(index))
        update.auto("/workshop/get/2/{}/".format(index), "upgrade_2_{}".format(index))
        update.auto("/workshop/get/reac/0/{}/".format(index), "reaction_0_{}".format(index))
        update.auto("/workshop/get/reac/1/{}/".format(index), "reaction_1_{}".format(index))
        update.auto("/workshop/get/reac/2/{}/".format(index), "reaction_2_{}".format(index))

# def pack_plots():
#     yield "<table>"
#     for i in range(20):
#         yield "<tr>"
#         for j in range(1):
#             yield "<td>"
#             yield Plot.show_plot(i + j)
#             yield "</td>"
#         yield "</tr>"
#     yield "</table>"


@app.route('/')
def home():
    response = make_response(render_template("game.html",
                                             resource_tree="\n".join(Resource.show_all()),
                                             plotnames = ["<div id=\"plot_name_{index}\"></div>".format(index =i)
                                                            for i in range(200)],
                                             plots=[Plot.show_plot(i) for i in range(200)],
                                             updater=update.get_html()))
    response.set_cookie('player_id', value=Player.get().id_)
    return response


# @app.route("/get_resourse/<js_id>/")
# def get_resources(js_id):
#     player = Player.get()
#     return str(player.get_resource(Resource.get_by_id(js_id)))


@app.route("/workshop/shift/<dir>/<index>/")
def shift_plot(dir, index):
    p = Player.get().plots[int(index)]
    p.active += {"left": -1, "right": 1}[dir]
    return '', 204

@app.route("/workshop/set/<newval>/<index>/")
def change_plot(newval, index):
    p = Player.get().plots[int(index)]
    p.active = int(newval)
    return '', 204


@app.route("/workshop/upgrade/<upgrade>/<index>/")
def upgrade_plot(upgrade, index):
    if int(index) >= len(Player.get().plots):
        return ""
    p = Player.get().plots[int(index)]
    upgrade = ([c for c in p.workshop.get_children()] + [None] * 3)[int(upgrade)]
    if upgrade is not None:
        p.change_workshop(upgrade)
    return '', 204

@app.route("/get/data/")
def get_data():
    p = Player.get()
    retdict = {"res_"+r.js_id:p.get_resource(r) for r in Resource.all_.values()}
    retdict.update({"resg_"+r.js_id:"{:+}".format(p.get_resource_gain(r)) for r in Resource.all_.values()})
    for i in range(200):
        if i >= len(p.plots):
            retdict.update({"plot_name_{}".format(i):"",
                            "plot_reaction_{}".format(i):"",
                            "upgrade_0_{}".format(i):"",
                            "upgrade_1_{}".format(i):"",
                            "upgrade_2_{}".format(i):"",
                            })
        else:
            plot = p.plots[i]
            retdict.update({"plot_name_{}".format(i):plot.workshop.name,
                            "plot_reaction_{}".format(i):plot.get_active(),
                            "upgrade_0_{}".format(i):([c.display for c in plot.workshop.get_children()] + [""] * 3)[0],
                            "upgrade_1_{}".format(i):([c.display for c in plot.workshop.get_children()] + [""] * 3)[1],
                            "upgrade_2_{}".format(i):([c.display for c in plot.workshop.get_children()] + [""] * 3)[2],
                            "reaction_0_{}".format(i):plot.get_inactive(0),
                            "reaction_1_{}".format(i):plot.get_inactive(1),
                            "reaction_2_{}".format(i):plot.get_inactive(2),
                            })
    return jsonify(retdict)


# @app.route("/workshop/get/name/<index>/")
# def get_w_name(index):
#     if int(index) >= len(Player.get().plots):
#         return ""
#     p = Player.get().plots[int(index)]
#     return p.workshop.name
#
#
# @app.route("/workshop/get/reaction/<index>/")
# def get_w_reac(index):
#     if int(index) >= len(Player.get().plots):
#         return ""
#     p = Player.get().plots[int(index)]
#     return p.get_active()
#
#
# @app.route("/workshop/get/<upgrade>/<index>/")
# def get_w_route(upgrade, index):
#     if int(index) >= len(Player.get().plots):
#         return ""
#     p = Player.get().plots[int(index)]
#     return ([c.display for c in p.workshop.get_children()] + [""] * 3)[int(upgrade)]


if __name__ == '__main__':
    update = Updater()
    Resource.load()
    Workshop.load()
    init_plots()
    forest = Workshop.all_[0]
    app.run()
