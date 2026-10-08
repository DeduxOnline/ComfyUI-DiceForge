# Node ids are shared by every node pack in ComfyUI, and when two packs use the same id, the one loaded last wins without a word: a workflow then
# opens with another pack's node. Every DiceForge id starts with DiceForge, so it can't clash (ComfyUI-RuiquNodes has a VAEDecodeSave, for one).
import asyncio
import DiceForge

IDS = [node.define_schema().node_id for node in asyncio.run(asyncio.run(DiceForge.comfy_entrypoint()).get_node_list())]


def test_every_node_id_starts_with_diceforge():
    assert [node_id for node_id in IDS if not node_id.startswith("DiceForge")] == []


def test_node_ids_are_unique():
    assert len(IDS) == len(set(IDS))
