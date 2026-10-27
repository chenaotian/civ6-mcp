"""Own-unit hex neighbors from native geometry, with no destination inspection.

Base/UI/AdjacencyBonusSupport.lua:91-109 uses the six DirectionTypes constants
and Map.GetAdjacentPlot. UnitFlagManager.lua:935-952 documents nil at a
non-wrapping map boundary and uses GetX/GetY on the returned plot.
"""
from .base import QuerySpec, lua, own_unit


_DIRECTIONS = [
    "DIRECTION_NORTHEAST", "DIRECTION_EAST", "DIRECTION_SOUTHEAST",
    "DIRECTION_SOUTHWEST", "DIRECTION_WEST", "DIRECTION_NORTHWEST",
]
_DESCRIPTION = "仅几何相邻坐标；不代表可通行、可达或安全，移动提交时仍会重新验证。"


def unit_neighbors(a: dict) -> str:
    return "out.supported=false\n" + own_unit(a["unit_id"]) + f'''
if not Map or type(Map.GetAdjacentPlot)~="function" or type(Map.GetGridSize)~="function"
    or not DirectionTypes then return end
local function integer(value,low,high)
    return type(value)=="number" and value==value and value%1==0 and value>=low and value<=high
end
local function collect()
    local width,height=Map.GetGridSize()
    if not integer(width,1,4096) or not integer(height,1,4096) then return nil end
    local x,y=unit:GetX(),unit:GetY()
    if not integer(x,0,width-1) or not integer(y,0,height-1) then return nil end
    if DirectionTypes.NUM_DIRECTION_TYPES~=6 then return nil end
    local directions,seen_directions={{}},{{}}
    for _,name in ipairs({lua(_DIRECTIONS)}) do
        local direction=DirectionTypes[name]
        if not integer(direction,0,5) or seen_directions[direction] then return nil end
        seen_directions[direction]=true
        directions[#directions+1]=direction
    end
    local items,seen={{}},{{}}
    for _,direction in ipairs(directions) do
        -- Only geometry. Never inspect terrain, occupancy, resources, sight,
        -- pathfinding or operation eligibility on this possibly unexplored hex.
        local plot=Map.GetAdjacentPlot(x,y,direction)
        if plot~=nil then
            if type(plot.GetX)~="function" or type(plot.GetY)~="function" then return nil end
            local nx,ny=plot:GetX(),plot:GetY()
            if not integer(nx,0,width-1) or not integer(ny,0,height-1) then return nil end
            nx,ny=math.floor(nx),math.floor(ny)
            local key=tostring(nx)..","..tostring(ny)
            if (nx~=x or ny~=y) and not seen[key] then
                seen[key]=true
                items[#items+1]={{id="neighbor:"..key,name="("..key..")",description={lua(_DESCRIPTION)},
                    scope="self",owner_id=me,
                    action={{type="move",unit_id={a['unit_id']},x=nx,y=ny}}}}
            end
        end
    end
    return items
end
local ok,items=pcall(collect)
if not ok or type(items)~="table" then return end
out.supported=true
for _,item in ipairs(items) do add_item(item) end
'''


ACTIONS = {}
QUERIES = {
    "unit_neighbors": QuerySpec({"unit_id": "id"}, unit_neighbors,
        "Native adjacent hex coordinates for an owned unit, including unexplored neighbors. "
        "Each item has a coordinate label and an existing move action. Geometry only: "
        "not passability, reachability, safety or permission to move now. No terrain, "
        "units, resources, visibility or pathfinding is read; move rechecks its normal guards."),
}
