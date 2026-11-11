# Node ids are shared by every node pack in ComfyUI, and when two packs use the same id, the one loaded last wins without a word: a workflow then
# opens with another pack's node. Every DiceForge id starts with DiceForge, so it can't clash (ComfyUI-RuiquNodes has a VAEDecodeSave, for one).
import asyncio
import sys
from comfy_api.latest import io
import DiceForge

NODES = asyncio.run(asyncio.run(DiceForge.comfy_entrypoint()).get_node_list())
IDS = [node.define_schema().node_id for node in NODES]


def test_every_node_id_starts_with_diceforge():
    assert [node_id for node_id in IDS if not node_id.startswith("DiceForge")] == []


def test_node_ids_are_unique():
    assert len(IDS) == len(set(IDS))


def test_random_int_and_float_are_in_the_utils_section():
    # The node library's sections: there is no random section, so the random numbers sit in utils with the other helpers.
    categories = {node.define_schema().node_id: node.define_schema().category for node in NODES}
    assert categories["DiceForgeRandomInt"] == categories["DiceForgeRandomFloat"] == "DiceForge/utils"
    assert "DiceForge/random" not in categories.values()


def test_every_node_is_registered_by_the_package():
    # ComfyUI only runs the package's comfy_entrypoint (DiceForge/__init__.py): a node left out of its list never shows up, and a module's own
    # entry point would never run.
    modules = [module for name, module in sys.modules.items() if name.startswith("DiceForge.")]
    defined = {value for module in modules for value in vars(module).values()
               if isinstance(value, type) and issubclass(value, io.ComfyNode) and value.__module__ == module.__name__}
    assert defined == set(NODES)
    assert [module.__name__ for module in modules if hasattr(module, "comfy_entrypoint")] == []
