local dir = debug.getinfo(1, "S").source:sub(2):match("^(.*)/[^/]+$")
local OpenBeat = assert(dofile(dir .. "/../../../Modules/OpenBeat/OpenBeatCommon.lua"))
OpenBeat.run("click_track", "quantized")
