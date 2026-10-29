"""Motion window routes (all owner-local).

- ``GET /api/v1/motion/catalog``: the motion engines, versions and sizes motion-lab has.
- ``GET /api/v1/motion/preview?name=previews/<file>.json``: one model's preview clip.
- ``GET /api/v1/motion/status``: what moves her now (the motion supervisor's state).
- ``POST /api/v1/motion/reload`` ``{"expected_revision": n}``: Reload motion model. It makes the
  saved ``motion.*`` settings active and restarts the motion engine while SORA runs, handing her
  over from her current pose (``sora.embodiment.motion_service``).

The engine choice itself is an ordinary ``motion.*`` settings edit.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from pydantic import ValidationError

from sora.api.protocol import HttpRequest, HttpResponse
from sora.embodiment.motion_catalog import load_catalog, load_preview
from sora.embodiment.motion_settings import MotionSettings
from sora.runtime.app_settings import ReloadRequest, SettingsConflict

if TYPE_CHECKING:
    from sora.embodiment.motion_service import MotionSupervisor
    from sora.runtime.app_settings import AppSettingsController

CATALOG = "/api/v1/motion/catalog"
PREVIEW = "/api/v1/motion/preview"
STATUS = "/api/v1/motion/status"
RELOAD = "/api/v1/motion/reload"
PATHS = frozenset({CATALOG, PREVIEW, STATUS})
POST_PATHS = frozenset({RELOAD})


def handle(path: str, request: HttpRequest, settings: MotionSettings, project: Path
           ) -> HttpResponse:
    """The read-only catalogue and previews."""
    if path == CATALOG:
        return HttpResponse.json(load_catalog(settings, project).model_dump(mode="json"))
    name = request.query_param("name", "") or ""
    try:
        return HttpResponse.json(load_preview(settings, project, name))
    except FileNotFoundError:
        return HttpResponse.error(404, "No such motion preview", code="NOT_FOUND")
    except (OSError, ValueError) as exc:
        return HttpResponse.error(422, str(exc)[:300], code="INVALID_INPUT")


def status(supervisor: MotionSupervisor | None) -> HttpResponse:
    if supervisor is None:
        return HttpResponse.json({"engine": "algorithmic", "state": "unavailable", "model": "",
                                  "error": "This Core has no motion engine (no avatar player).",
                                  "load_seconds": None, "chunks": 0,
                                  "player_connected": False})
    return HttpResponse.json(supervisor.status())


async def reload(request: HttpRequest, controller: AppSettingsController,
                 supervisor: MotionSupervisor | None) -> HttpResponse:
    if supervisor is None:
        return HttpResponse.error(409, "Her avatar player isn't running, so there's no motion "
                                       "engine to reload.", code="UNAVAILABLE")
    try:
        edit = ReloadRequest.model_validate(request.json() or {})
        projection = controller.apply_motion(edit)
    except SettingsConflict as exc:  # a ValueError, so first
        return HttpResponse.error(409, str(exc), code="CONFLICT")
    except (ValidationError, ValueError) as exc:
        return HttpResponse.error(400, str(exc)[:300], code="INVALID_INPUT")
    result = await supervisor.reload(controller.active.motion)
    return HttpResponse.json({"motion": result, "settings": projection})
