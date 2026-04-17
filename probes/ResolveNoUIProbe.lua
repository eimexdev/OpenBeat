local function write_log(message)
  local path = os.getenv("HOME") .. "/Library/Application Support/Blackmagic Design/DaVinci Resolve/logs/OpenBeatProbe.log"
  local handle = assert(io.open(path, "a"))
  handle:write(os.date("%Y-%m-%d %H:%M:%S "), message, "\n")
  handle:close()
end

local resolve = resolve or app:GetResolve()
if not resolve then
  write_log("Resolve object unavailable")
  return
end

local project_manager = resolve:GetProjectManager()
local project = project_manager and project_manager:GetCurrentProject()
local timeline = project and project:GetCurrentTimeline()
local timeline_name = timeline and timeline:GetName() or "<no timeline>"

write_log("No-UI probe ran successfully. Timeline: " .. timeline_name)
print("OpenBeat no-UI probe ran. Timeline: " .. timeline_name)
