"""Own-city district condition fields from the normal city/plot UI.

GS CitySupport.lua:629,657-668 and PlotToolTip.lua:749-762 use the own
district type plus plot index for IsPillaged/IsComplete. No district yields,
adjacency, neighboring plots, or foreign collections are inspected here.
"""


CITY_DISTRICT_HELPERS = r'''
local function add_city_district_conditions()
    local districts=city_cost_read(city,'GetDistricts')
    if not districts or type(districts.Members)~='function' or not GameInfo.Districts then return end
    local count,seen=0,{}
    for _,district in districts:Members() do
        count=count+1;if count>256 then error('unavailable') end
        local kind=city_cost_read(district,'GetType')
        local x,y=city_cost_read(district,'GetX'),city_cost_read(district,'GetY')
        if city_cost_index(kind) and city_cost_index(x) and city_cost_index(y) then
            local plot=visible_plot(x,y)
            if plot and plot:GetOwner()==me then
                local index=city_cost_read(plot,'GetIndex')
                local row=GameInfo.Districts[kind]
                if city_cost_index(index) and row and type(row.DistrictType)=='string'
                    and row.DistrictType:match('^DISTRICT_[A-Z0-9_]+$') and not seen[index] then
                    seen[index]=true
                    local prefix='district:'..math.floor(index)
                    local function field(suffix,name,value)
                        add(prefix..suffix,name,nil,value)
                        out.items[#out.items].x=math.floor(x)
                        out.items[#out.items].y=math.floor(y)
                    end
                    field('',row.Name,row.DistrictType)
                    -- The public flat-item projection retains scalar values,
                    -- not raw coordinate proof fields, so publish both values.
                    field(':x','区域地块横坐标',math.floor(x))
                    field(':y','区域地块纵坐标',math.floor(y))
                    for suffix,method in pairs({complete='IsComplete',pillaged='IsPillaged'}) do
                        local value=city_cost_read(districts,method,kind,index)
                        if type(value)=='boolean' then
                            field(':'..suffix,suffix=='complete' and '区域已完成' or '区域遭到掠夺',value)
                        end
                    end
                end
            end
        end
    end
end
'''
