from camo.api.routes.characters import router as characters_router
from camo.api.routes.consistency import router as consistency_router
from camo.api.routes.demo import router as demo_router
from camo.api.routes.events import router as events_router
from camo.api.routes.feedbacks import router as feedbacks_router
from camo.api.routes.modeling import router as modeling_router
from camo.api.routes.projects import router as projects_router
from camo.api.routes.relationships import router as relationships_router
from camo.api.routes.reviews import router as reviews_router
from camo.api.routes.runtime import router as runtime_router
from camo.api.routes.system import router as system_router
from camo.api.routes.texts import router as texts_router

__all__ = [
    "characters_router",
    "consistency_router",
    "demo_router",
    "events_router",
    "feedbacks_router",
    "modeling_router",
    "projects_router",
    "relationships_router",
    "reviews_router",
    "runtime_router",
    "system_router",
    "texts_router",
]
