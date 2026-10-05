"""The changelog convention every agent is held to.

Two things live here and only two: the directory name, and the instruction carried by every agent
prompt. Core does not write these entries - the agent does, because the agent is the one that knows
what it actually did, and an agent of materially higher capability than the dialogue core should be
the author of its own account. Core verifies what arrives and reports the gap when nothing does; it
never composes an entry itself.
"""

CHANGELOG_DIRECTORY = "changelog"

CHANGELOG_INSTRUCTION = (
    "Before you finish, write your own changelog entry for this task. Create the file "
    f"`{CHANGELOG_DIRECTORY}/<UTC timestamp>_<SHORT-SLUG>_<YOUR-NAME>.md` in your working "
    "directory, creating the folder if it does not exist. State what you changed, why you changed "
    "it, which files you touched and how you checked your work; be specific and do not pad it. "
    "Write it yourself - do not ask Core to summarise your work for you, and do not treat this "
    "instruction as optional. Then return its path, relative to your working directory, as "
    "changelog_path. If you genuinely cannot create files (a read-only sandbox), return the same "
    "entry text as changelog_entry instead and Core will store it verbatim, attributed to you."
)
