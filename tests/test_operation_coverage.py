"""Source-catalog coverage and syntax validation across the public registry.

The XML check is deliberately scoped to Base/Rise and Fall/Gathering Storm.
It validates mapping coverage, not real-game behavior or optional-mode support.
"""
from copy import deepcopy
from pathlib import Path
import os
import xml.etree.ElementTree as ET

import pytest
from lupa import LuaRuntime

from civ6_fair_mcp.actions import build_action_query, validate_action
from civ6_fair_mcp.extensions import registries, build_inspection_query
from civ6_fair_mcp.extensions.base import validate
from civ6_fair_mcp.extensions import units
from test_extension_units import engine as unit_engine


INSTALL = Path(os.environ.get('CIV6_INSTALL', "F:/SteamLibrary/steamapps/common/Sid Meier's Civilization VI"))
DATA_DIRS = ('Base/Assets/Gameplay/Data', 'DLC/Expansion1/Data', 'DLC/Expansion2/Data')


def engine_catalog():
    tables = {'UnitOperations': {}, 'UnitCommands': {}}
    for relative in DATA_DIRS:
        for file in sorted((INSTALL / relative).glob('*Unit*.xml')):
            root = ET.parse(file)
            for table, field in (('UnitOperations', 'OperationType'), ('UnitCommands', 'CommandType')):
                for row in root.findall(f'./{table}/Row'):
                    if row.get(field):
                        tables[table][row.get(field)] = row.attrib.copy()
                for update in root.findall(f'./{table}/Update'):
                    where, values = update.find('Where'), update.find('Set')
                    if where is not None and values is not None and where.get(field) in tables[table]:
                        patch = values.attrib.copy()
                        patch.update({child.tag: child.text for child in values})
                        tables[table][where.get(field)].update(patch)
    return tables


def supported_operations():
    return (set(units.ORDERS.values()) | set(units.SPY_MISSIONS)
            | {op for family, op in units.TARGETS.values() if family == 'operation'}
            | {'MOVE_TO','FORTIFY','FOUND_CITY','BUILD_IMPROVEMENT','MAKE_TRADE_ROUTE',
               'TELEPORT_TO_CITY','SPY_TRAVEL_NEW_CITY','BUILD_IMPROVEMENT_ADJACENT','WMD_STRIKE','SWAP_UNITS'})


def supported_commands():
    return (set(units.COMMANDS.values())
            | {op for family, op in units.TARGETS.values() if family == 'command'}
            | {'PROMOTE','NAME_UNIT','FORM_CORPS','FORM_ARMY','ENTER_FORMATION'})


@pytest.mark.skipif(not (INSTALL / DATA_DIRS[0]).exists(), reason='optional read-only installed Civ6 source audit')
def test_all_baseline_visible_unit_rows_have_curated_mappings():
    tables = engine_catalog()
    operations = {name.removeprefix('UNITOPERATION_') for name, row in tables['UnitOperations'].items() if row.get('VisibleInUI') == 'true'}
    commands = {name.removeprefix('UNITCOMMAND_') for name, row in tables['UnitCommands'].items() if row.get('VisibleInUI') == 'true'}
    assert len(operations) >= 55 and len(commands) >= 26
    assert operations <= supported_operations()
    assert commands <= supported_commands()
    assert 'EXECUTE_SCRIPT' not in supported_operations() | supported_commands()
    # The only invisible operation deliberately exposed is the stock right-click
    # SWAP_UNITS path, with two own actors; hidden arbitrary-script paths stay out.
    for key in supported_operations() - operations:
        assert key == 'SWAP_UNITS'


def sample(schema):
    if isinstance(schema, dict):
        return {key: sample(value) for key, value in schema.items()}
    if isinstance(schema, list):
        return [sample(schema[0])]
    if schema in {'id','signed_id','coord'}:
        return 1
    if schema == 'number':
        return 1.5
    if schema == 'bool':
        return False
    if schema == 'text':
        return '测试 "name" \\ literal'
    if schema == 'text_identifier':
        return 'TEST'
    if schema.startswith('identifier:'):
        return schema[11:].split('|')[0] + 'TEST'
    if schema.startswith('enum:'):
        return schema[5:].split('|')[0]
    raise AssertionError(schema)


def variants(fields):
    original = sample(fields)
    yield original
    # At least one execution of every fixed top-level enum branch. Nested list
    # handling uses nonempty data so compiled branches aren't merely empty loops.
    for key, schema in fields.items():
        if isinstance(schema, str) and schema.startswith('enum:'):
            for value in schema[5:].split('|')[1:]:
                changed = deepcopy(original)
                changed[key] = value
                yield changed
        elif schema == 'bool':
            changed = deepcopy(original)
            changed[key] = True
            yield changed


def test_all_registered_action_schemas_and_generated_lua_compile():
    actions, _ = registries()
    vm = LuaRuntime()
    for name, spec in actions.items():
        for args in variants(spec.fields):
            action = {'type': name, **args}
            assert validate_action(action) == action, name
            source = build_action_query('audit', action, 'audit', 0, 1)
            try:
                vm.compile(source, name=name)
            except Exception as exc:
                raise AssertionError(f'{name}: {args}') from exc


def test_all_registered_inspection_schemas_and_generated_lua_compile():
    _, queries = registries()
    vm = LuaRuntime()
    for name, spec in queries.items():
        for args in variants(spec.fields):
            assert validate(args, spec.fields) == args, name
            try:
                vm.compile(build_inspection_query('audit', name, args), name=name)
            except Exception as exc:
                raise AssertionError(f'{name}: {args}') from exc


@pytest.mark.parametrize('order,expected',[('activate_prophet','FOUND_RELIGION'),('evangelize_belief','EVANGELIZE_BELIEF')])
def test_religious_ability_trigger_is_separate_from_belief_choice(unit_engine,order,expected):
    vm, run = unit_engine
    result = run('unit_order', {'unit_id':10,'order':order})
    assert result['accepted']
    assert vm.globals().calls[1]['kind']=='operation'
    assert vm.globals().calls[1]['op']==vm.globals().UnitOperationTypes[expected]


def test_unit_rename_uses_normal_command_and_literal_name(unit_engine):
    vm, run = unit_engine
    vm.execute('GameCapabilities={HasCapability=function(s) return s=="CAPABILITY_RENAME" end};UnitCommandTypes.PARAM_NAME="name"')
    result = run('unit_rename', {'unit_id':10,'name':'勇士 "甲"'})
    assert result['accepted']
    assert vm.globals().calls[1]['params']['name']=='勇士 "甲"'
    assert vm.globals().calls[1]['op']==vm.globals().UnitCommandTypes.NAME_UNIT


def test_swap_requires_two_own_adjacent_actors(unit_engine):
    vm, run = unit_engine
    vm.execute('other.GetX=function() return 3 end;other.GetY=function() return 2 end')
    result = run('unit_swap', {'unit_id':10,'other_unit_id':11})
    assert result['accepted']
    assert vm.globals().calls[1]['op']==vm.globals().UnitOperationTypes.SWAP_UNITS
    assert vm.globals().calls[1]['params']['x']==3
    vm.execute('other.GetOwner=function() return 1 end;other.GetX=forbidden;other.GetY=forbidden')
    result = run('unit_swap', {'unit_id':10,'other_unit_id':11})
    assert not result['accepted']
    assert vm.globals().reads.hidden==0


def test_swap_discovery_offers_actual_own_target(unit_engine):
    vm, run = unit_engine
    vm.execute('other.GetX=function() return 3 end;other.GetY=function() return 2 end')
    result = run('unit_swaps', {'unit_id':10}, query=True)
    assert result['items'][0]['action']=={'type':'unit_swap','unit_id':10,'other_unit_id':11}
