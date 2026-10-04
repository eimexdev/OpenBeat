local Timing = dofile("resolve/Fusion/Modules/OpenBeat/OpenBeatTiming.lua")

local function equal(actual, expected)
  assert(actual == expected, tostring(actual) .. " ~= " .. tostring(expected))
end

equal(Timing.timecode_to_frame("01:00:00:00", 24), 86400)
equal(Timing.timecode_to_frame("01:00:00:00", 23.976), 86400)
equal(Timing.timecode_to_frame("01:00:00:00", 24000 / 1001), 86400)
equal(Timing.timecode_to_frame("01:00:00:00", 29.97), 108000)
equal(Timing.timecode_to_frame("01:00:00:00", 59.94), 216000)
equal(Timing.timecode_to_frame("00:00:59;29", 29.97), 1799)
equal(Timing.timecode_to_frame("00:01:00;02", 29.97), 1800)
equal(Timing.timecode_to_frame("00:10:00;00", 29.97), 17982)
equal(Timing.timecode_to_frame("01:00:00;00", 30000 / 1001), 107892)
equal(Timing.timecode_to_frame("01:00:00:00", 29.97, true), 107892)
equal(Timing.timecode_to_frame("01:00:00;00", 59.94), 215784)
equal(Timing.timecode_to_frame("00:01:00;04", 59.94), 3600)

for _, tc in ipairs({ "00:01:00;00", "00:01:00;01", "00:60:00:00", "00:00:00:30", "bad", "x01:00:00:00" }) do
  assert(not pcall(Timing.timecode_to_frame, tc, 29.97), "Accepted invalid timecode " .. tc)
end
assert(not pcall(Timing.timecode_to_frame, "01:00:00;00", 24))

local fps, drop_frame = Timing.frame_rate("29.97 DF")
equal(fps, 29.97)
assert(drop_frame)
fps, drop_frame = Timing.frame_rate({ timelineFrameRate = "59.94 DF" })
equal(fps, 59.94)
assert(drop_frame)
fps, drop_frame = Timing.frame_rate("23.976")
equal(fps, 23.976)
assert(not drop_frame)
assert(not pcall(Timing.frame_rate, "invalid"))
