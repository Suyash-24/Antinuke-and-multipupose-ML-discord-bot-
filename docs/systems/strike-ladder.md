# Strike Ladder

Aegis uses strikes to separate detection from punishment.

## How it works

1. A user triggers an AutoMod rule or receives manual moderator strikes.
2. Their active strike total increases.
3. Aegis checks the punishment ladder.
4. If a threshold is reached, Aegis applies the matching action.

## Example ladder

- `1` strike -> warn
- `3` strikes -> mute for `1h`
- `5` strikes -> ban

## Why this is useful

The ladder gives staff consistency:

- low-level spam can be warned
- repeat behavior escalates without custom judgment every time
- moderators can pardon mistakes without rewriting history

## Related commands

- `^punishment`
- `^strike`
- `^pardon`
- `^check`
