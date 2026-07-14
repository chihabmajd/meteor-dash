-- meteor-dash mpv history hook
-- Logs every file you play (and how far you got) to a JSONL file that
-- meteor-dash reads for precise "watched" detection.
--
-- Install:  copy to ~/.config/mpv/scripts/mpv-history.lua
--           (scripts/install.sh does this for you)
--
-- Each line: {"path":..,"filename":..,"pos":<seconds>,"duration":<seconds>,"ts":<epoch>}
-- meteor-dash treats a file played past `finished_fraction` (default 0.85) as watched.

local mp = require 'mp'
local utils = require 'mp.utils'

local home = os.getenv("HOME") or ""
local dir = home .. "/.config/meteor-dash"
local logpath = dir .. "/mpv-history.jsonl"
os.execute('mkdir -p "' .. dir .. '" 2>/dev/null')

local last_pos, duration, path = 0, 0, nil

mp.observe_property("time-pos", "number", function(_, v)
    if v and v > last_pos then last_pos = v end
end)
mp.observe_property("duration", "number", function(_, v)
    if v then duration = v end
end)
mp.register_event("file-loaded", function()
    path = mp.get_property("path")
    last_pos, duration = 0, 0
end)

local function flush()
    if not path then return end
    local rec = utils.format_json({
        path = path,
        filename = mp.get_property("filename") or path,
        pos = last_pos,
        duration = duration,
        ts = os.time(),
    })
    local f = io.open(logpath, "a")
    if f then f:write(rec .. "\n"); f:close() end
    path = nil
end

mp.register_event("end-file", flush)
mp.register_event("shutdown", flush)
