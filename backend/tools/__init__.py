from .state import update_canvas_state, canvas_action_queue, canvas_state
from .spatial_read import (
    get_viewport_context, get_canvas_map, get_nearby_shapes,
    get_arrow_connections, find_shape_by_text, get_selected_shapes, get_shapes_in_region
)
from .smart_write import place_near, place_in_empty_space, place_relative
from .organize import (
    align_shapes, distribute_shapes, stack_shapes,
    resize_shape, rotate_shapes, bring_to_front, send_to_back,
    set_viewport, create_frame, group_shapes,
)
from .semantic import label_shape, get_semantic_graph
from .basic_write import (
    list_canvas_shapes, scan_canvas_text, memory_read, memory_write,
    add_text_to_canvas, add_note_to_canvas, add_geo_to_canvas, add_arrow_to_canvas,
    bind_arrow, add_embed_to_canvas, add_bookmark_to_canvas, move_shape,
    update_shape, delete_shapes, zoom_to_fit, focus_shape, select_shapes, clear_canvas,
    undo_last_action, redo_last_action,
)
from .pen_draw import draw_freehand
from .agent_state import think, todo_update, schedule_review
from .dispatch import (
    dispatch_research, dispatch_image_gen, dispatch_youtube,
    dispatch_super_think, dispatch_document,
    defer_task, check_deferred_tasks,
)

ALL_TOOLS = [
    # Internal state — think first, then act
    think,
    todo_update,
    schedule_review,

    # Spatial read
    get_viewport_context, get_canvas_map, get_nearby_shapes,
    get_arrow_connections, get_shapes_in_region, find_shape_by_text, get_selected_shapes,

    # Smart placement
    place_near, place_in_empty_space, place_relative,

    # Organize
    align_shapes, distribute_shapes, stack_shapes,
    resize_shape, rotate_shapes, bring_to_front, send_to_back,
    set_viewport, create_frame, group_shapes,

    # Semantic
    label_shape, get_semantic_graph,

    # Basic read
    list_canvas_shapes, scan_canvas_text, memory_read, memory_write,

    # Basic write
    add_text_to_canvas, add_note_to_canvas, add_geo_to_canvas, add_arrow_to_canvas,
    bind_arrow, add_embed_to_canvas, add_bookmark_to_canvas, move_shape,
    update_shape, delete_shapes, focus_shape, select_shapes, clear_canvas,
    undo_last_action, redo_last_action,

    # Navigate
    zoom_to_fit,

    # Freehand
    draw_freehand,

    # Dispatch
    dispatch_research, dispatch_image_gen, dispatch_youtube,
    dispatch_super_think, dispatch_document,
    defer_task, check_deferred_tasks,
]

__all__ = [
    "ALL_TOOLS",
    "update_canvas_state",
    "canvas_action_queue",
    "canvas_state",
]
