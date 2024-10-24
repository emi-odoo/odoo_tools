import ast
import os
from collections import defaultdict
from itertools import chain
import csv

addons_paths = {
    "custom_old": [],
    "custom_new": [],
    "std_old": [],
    "std_new": [],
}
# models[ttype][model._name] = {'fields': fields, 'methods': methods}
models = {k: defaultdict(lambda: {"fields": set(), "methods": set()}) for k in addons_paths}
# MAP represents the possible outcomes of the comparison between the old and new version of a field/method
MAP_IN = {
    (1, 1, 1, 1): "perfect",
    (1, 1, 1, 0): "missing_new_std",
    (1, 1, 0, 1): "conflict",
    (1, 1, 0, 0): "perfect",
    (1, 0, 1, 1): "forgotten",
    (1, 0, 1, 0): "might_have_been_replaced",
    (1, 0, 0, 1): "might_have_been_replaced",
    (1, 0, 0, 0): "might_have_been_replaced",
    (0, 1, 1, 1): "to_check",
    (0, 1, 1, 0): "conflict",
    (0, 1, 0, 1): "might_be_replacement",
    (0, 1, 0, 0): "might_be_replacement",
    (0, 0, 1, 1): "impossible",
    (0, 0, 1, 0): "impossible",
    (0, 0, 0, 1): "impossible",
    (0, 0, 0, 0): "impossible",
}
MAPPING_TYPE = set(MAP_IN.values())


def _find_model(class_):
    model = None
    for assign in (elem for elem in class_.body if isinstance(elem, ast.Assign)):
        if not isinstance(assign.targets[0], ast.Name):
            continue
        target_id = getattr(assign.targets[0], "id", None)
        if target_id not in ("_inherit", "_name"):
            continue
        if isinstance(assign.value, ast.Constant):
            model = assign.value.value
        elif isinstance(assign.value, ast.List):
            model = assign.value.elts[0].value
        if model:
            break
    return model


def _find_fields(class_):
    fields = set()
    for assign in (elem for elem in class_.body if isinstance(elem, ast.Assign)):
        if not isinstance(assign.value, ast.Call):
            continue
        # we need to check if `assign.value.func.value.id` is equal to `fields`
        if not hasattr(assign.value.func, "value"):
            continue
        if not hasattr(assign.value.func.value, "id"):
            continue
        if assign.value.func.value.id != "fields":
            continue
        fields.add(assign.targets[0].id)

    return fields


def _find_methods(class_):
    methods = set()
    for elem in class_.body:
        if isinstance(elem, ast.FunctionDef):
            methods.add(elem.name)

    return methods


# Get all function/fields names with their associated class
for ttype, paths in addons_paths.items():
    for addons_path in paths:
        for root, subdirs, fnames in os.walk(addons_path):
            for fname in fnames:
                if not fname.endswith(".py") or "migration" in root or "tests" in root:
                    continue
                fpath = f"{root}/{fname}"
                with open(fpath) as file:
                    node = ast.parse(file.read())
                    for class_ in [elem for elem in node.body if isinstance(elem, ast.ClassDef)]:
                        model = _find_model(class_)
                        if not model:
                            continue
                        models[ttype][model]["fields"] |= _find_fields(class_)
                        models[ttype][model]["methods"] |= _find_methods(class_)


def _check_models(models_to_check, check_type="fields"):
    """

    :param models_to_check: dict
    :param check_type: str
    :return: dict of type {model: {"type": "", "missing": set(), "extra": set(), "ok": set()}}
        - type can be "missing_old", "missing_new", "perfect"
        - missing is the set of fields/methods that are missing in the new version
        - extra is the set of fields/methods that are extra in the new version
        - ok is the set of fields/methods that are the same in both versions

    """

    all_models = {
        model for model in chain.from_iterable((values for key, values in models_to_check.items() if key.startswith("custom")))
    }
    result_fields = []
    for model in all_models:
        old_custom = models_to_check["custom_old"].get(model, {check_type: set()}).get(check_type, set())
        new_custom = models_to_check["custom_new"].get(model, {check_type: set()}).get(check_type, set())
        old_std = models_to_check["std_old"].get(model, {check_type: set()}).get(check_type, set())
        new_std = models_to_check["std_new"].get(model, {check_type: set()}).get(check_type, set())
        all_fields = old_custom | new_custom
        for field in all_fields:
            mapping, tuple_in = _check_field_mapping(field, old_custom, new_custom, old_std, new_std)
            result_fields.append([model, mapping, field, *tuple_in])
    return result_fields


def _check_field_mapping(field, old_custom_fields, new_custom_fields, old_std_fields, new_std_fields):
    tuple_in = (field in old_custom_fields, field in new_custom_fields, field in old_std_fields, field in new_std_fields)
    return MAP_IN[tuple_in], tuple_in


def _output_csv(fields, outfile):
    out = csv.writer(open(outfile, "w"))
    out.writerow(["model", "type", "record", "in_old_custom", "in_new_custom", "in_old_std", "in_new_std"])
    out.writerows(fields)


fields_check = _check_models(models, "fields")
methods_check = _check_models(models, "methods")
_output_csv(fields_check, "fields_check.csv")
_output_csv(methods_check, "methods_check.csv")
