"""Barra de menús propia (botones de menú) para poder darle estilo a los menús
desplegables, que GTK crea fuera del árbol de la ventana."""
import gi
gi.require_version("Gtk", "4.0")
from gi.repository import Gtk


def build_menubar(model, btn_class, pop_class):
    """model: Gio.Menu cuyos elementos son submenús. Devuelve un Gtk.Box con un
    botón por submenú. Si hay un menú abierto, pasar el ratón por otro lo abre."""
    box = Gtk.Box()
    buttons = []
    for i in range(model.get_n_items()):
        label = model.get_item_attribute_value(i, "label", None).get_string()
        sub = model.get_item_link(i, "submenu")
        mb = Gtk.MenuButton()
        mb.set_child(Gtk.Label(label=label))
        mb.set_menu_model(sub)
        mb.set_has_frame(False)
        mb.set_always_show_arrow(False)
        mb.set_focus_on_click(False)
        mb.add_css_class(btn_class)
        pop = mb.get_popover()
        pop.add_css_class(pop_class)
        pop.set_has_arrow(False)
        buttons.append(mb)
        box.append(mb)

    def hover(_ctrl, _x, _y, me):
        for other in buttons:
            if other is not me and other.get_popover().is_visible():
                other.popdown(); me.popup(); return

    for mb in buttons:
        m = Gtk.EventControllerMotion()
        m.connect("enter", hover, mb)
        mb.add_controller(m)
    return box
