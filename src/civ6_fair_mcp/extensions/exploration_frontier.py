"""Bounded exploration planning derived solely from local visibility labels."""
from .base import QuerySpec

CATEGORY = "exploration_frontier"
FIELDS = {"offset": "id"}
PAGE_SIZE = 512
MAX_PLOTS = 65536


def exploration_frontier(a: dict) -> str:
    return f'''
out.supported=false
local offset={a['offset']}
local function integer(v,lo,hi)
    return type(v)=='number' and v==v and v%1==0 and v>=lo and v<=hi
end
local function collect_frontier()
    if not Map or type(Map.GetGridSize)~='function' or type(Map.GetAdjacentPlot)~='function'
        or not vis or type(vis.IsRevealed)~='function' or type(vis.IsVisible)~='function'
        or not UI or type(UI.IsGameCoreBusy)~='function' or UI.IsGameCoreBusy()~=false then return end
    local width,height=Map.GetGridSize()
    if not integer(width,1,4096) or not integer(height,1,4096) or width*height>{MAX_PLOTS}
        or offset>width*height then return end
    local stop=math.min(offset+{PAGE_SIZE},width*height)
    local rows={{}}
    for index=offset,stop-1 do
        local x,y=index%width,math.floor(index/width)
        local revealed=vis:IsRevealed(x,y)
        if type(revealed)~='boolean' then return end
        if revealed then
            local boundary=false
            for direction=0,5 do
                -- Geometry only. No terrain, owner, resource, city or unit read.
                -- Native adjacency preserves horizontal wrap and hex layout.
                local adjacent=Map.GetAdjacentPlot(x,y,direction)
                if adjacent then
                    if type(adjacent.GetX)~='function' or type(adjacent.GetY)~='function' then return end
                    local ax,ay=adjacent:GetX(),adjacent:GetY()
                    if not integer(ax,0,width-1) or not integer(ay,0,height-1) then return end
                    local neighbor=vis:IsRevealed(ax,ay)
                    if type(neighbor)~='boolean' then return end
                    if neighbor==false then boundary=true end
                end
            end
            if boundary then
                local visible=vis:IsVisible(x,y)
                if type(visible)~='boolean' then return end
                rows[#rows+1]={{x=math.floor(x),y=math.floor(y),revealed=true,
                    visible=visible,adjacent_unrevealed=true}}
            end
        end
    end
    if UI.IsGameCoreBusy()~=false then return end
    -- These are candidate directions, never reachability or safe-move promises.
    out.frontier={{source='local_visibility_labels',owner_id=me,offset=offset,
        width=math.floor(width),height=math.floor(height),next_offset=stop<width*height and math.floor(stop) or -1}}
    out.items=array(rows)
    out.supported=true
end
collect_frontier()
'''


ACTIONS = {}
QUERIES = {CATEGORY: QuerySpec(FIELDS, exploration_frontier,
    "Page explored boundary coordinates adjoining unexplored hexes (offset=0 first, then next_offset). "
    "Only local visibility labels; no fog contents, hidden resources, route or safety prediction. "
    "Scans at most 512 map cells per page; next_offset=-1 ends this scan.")}
