from graphviz import Digraph
import os
import ast

dot = Digraph(comment="Odoo Modules")


def find_modules(main_path):
    modules = {}
    for root, dirs, files in os.walk(main_path):
        if "__manifest__.py" not in files:
            continue
        # get the name of the module from the path
        modules[root.split("/")[-1]] = root

    return modules


def find_dependencies(module_path):
    # read __manifest__.py
    manifest_path = os.path.join(module_path, "__manifest__.py")
    with open(manifest_path, "r") as f:
        manifest_content = f.read()
        manifest_content = ast.literal_eval(manifest_content)
    return set(manifest_content.get("depends", []))


def build_network(module_path):
    modules = find_modules(module_path)
    modules_names = set(modules.keys())
    for module_name in modules_names:
        dot.node(module_name, label=module_name)
    for module_name, module_path in find_modules(module_path).items():
        for dependency in find_dependencies(module_path):
            if dependency in modules_names:
                dot.edge(dependency, module_name)
    dot.render("odoo_modules_graph", format="dot", view=True)


if __name__ == "__main__":
    build_network(os.getcwd())
