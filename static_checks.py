"""Static pre-render checks for the video-iteration harness.

Independent of the core pipeline (pipeline_deepseek.py / local_agent.py):
this module only adds AST-level gates that catch render-time bug classes
BEFORE a render is spent. It imports nothing from the pipeline.

Checks:
  find_undefined_self_attrs       self.X read but never assigned anywhere
  find_premature_self_attrs       self.X read in an always_redraw callback
                                  whose first assignment comes AFTER the
                                  callback (always_redraw fires immediately)
  find_readonly_self_assignments  self.X = ... where X is a read-only Manim
                                  property (e.g. Scene.time)
  find_loop_play_risks            for/while loop whose body calls self.play or
                                  builds heavy mobjects per iteration without a
                                  provably small literal bound (render timeout)
  find_unknown_methods            attribute-method calls that do not exist on
                                  the receiver's Manim class (e.g. the
                                  hallucinated set_points_smooth) - the biggest
                                  render-hang driver

Usage:
    from static_checks import find_undefined_self_attrs
"""
import ast

import manim

_MANIM_SELF_CLASSES = (
    "Scene", "MovingCameraScene", "ThreeDScene", "ZoomedScene",
    "AnimationBuilder", "Mobject", "VMobject", "Group", "VGroup",
    "Text", "Tex", "MathTex", "Camera", "MovingCamera", "ThreeDCamera",
    "ValueTracker", "SceneFileWriter",
)


def _manim_self_whitelist() -> set:
    """Attribute names available on a live Scene instance without user code."""
    attrs = set()
    for name in _MANIM_SELF_CLASSES:
        obj = getattr(manim, name, None)
        if obj is None:
            continue
        attrs.update(dir(obj))
    return attrs


def _manim_readonly_properties() -> set:
    """Manim attributes that are properties and cannot be assigned (fset None)."""
    names = set()
    for name in _MANIM_SELF_CLASSES:
        obj = getattr(manim, name, None)
        if obj is None:
            continue
        for attr in dir(obj):
            try:
                value = getattr(obj, attr)
            except Exception:
                continue
            if isinstance(value, property) and value.fset is None:
                names.add(attr)
    return names


def _self_attr_reads(subtree) -> set:
    reads = set()
    for node in ast.walk(subtree):
        if (
            isinstance(node, ast.Attribute)
            and isinstance(node.value, ast.Name)
            and node.value.id == "self"
            and isinstance(node.ctx, ast.Load)
        ):
            reads.add(node.attr)
    return reads


def _self_attr_stores(subtree) -> set:
    stores = set()

    def _mark(target) -> None:
        if (
            isinstance(target, ast.Attribute)
            and isinstance(target.value, ast.Name)
            and target.value.id == "self"
        ):
            stores.add(target.attr)

    for node in ast.walk(subtree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                _mark(target)
        elif isinstance(node, (ast.AugAssign, ast.AnnAssign)):
            _mark(node.target)
    return stores


def _class_methods(tree) -> set:
    methods = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            for stmt in node.body:
                if isinstance(stmt, ast.FunctionDef):
                    methods.add(stmt.name)
    return methods


def _is_always_redraw(call: ast.Call) -> bool:
    func = call.func
    if isinstance(func, ast.Name):
        return func.id in ("always_redraw", "AlwaysRedraw")
    if isinstance(func, ast.Attribute):
        return func.attr in ("always_redraw", "AlwaysRedraw")
    return False


def find_undefined_self_attrs(code: str) -> list[str]:
    """Return self.X reads that are never assigned anywhere as self.X and are
    not Manim base attributes.

    Catches render-time bugs before a render is spent, e.g. an updater reading
    self.current_velocity that is never set anywhere in the class. Method names
    defined on the scene class count as defined (self.get_ball() is fine).
    """
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return []

    whitelist = _manim_self_whitelist()
    defined = _class_methods(tree) | _self_attr_stores(tree)

    reads = _self_attr_reads(tree)

    return sorted(reads - whitelist - defined)


def find_premature_self_attrs(code: str) -> list[str]:
    """Return self.X read inside an always_redraw/AlwaysRedraw callback whose
    first assignment in the enclosing function comes AFTER the callback.

    always_redraw builds its mobject immediately at call time, so reading an
    attribute assigned later in construct raises AttributeError before the
    animation starts (e.g. self.anim_time assigned after the arrow updaters).
    """
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return []

    whitelist = _manim_self_whitelist()
    methods = _class_methods(tree)
    flags = set()

    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef):
            continue
        assigned_before = set()
        for stmt in node.body:
            assigned_before |= _self_attr_stores(stmt)
            for call in ast.walk(stmt):
                if not isinstance(call, ast.Call) or not _is_always_redraw(call):
                    continue
                for arg in call.args:
                    for attr in _self_attr_reads(arg):
                        if attr not in whitelist and attr not in methods and attr not in assigned_before:
                            flags.add(attr)

    return sorted(flags)


def find_readonly_self_assignments(code: str) -> list[str]:
    """Return self.X assignments where X is a read-only Manim property
    (e.g. Scene.time), which raises AttributeError at render time."""
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return []

    readonly = _manim_readonly_properties()
    assigned = _self_attr_stores(tree)

    return sorted(assigned & readonly)


_MANIM_3D_SOURCES = (
    "coords_to_point", "get_center", "get_start", "get_end", "get_top",
    "get_bottom", "get_left", "get_right", "get_arc_center",
    "point_from_proportion", "get_corner", "get_edge_center",
    "get_vertices", "get_bezier_control_points",
)
_MANIM_3D_CONSTANTS = ("ORIGIN", "UP", "DOWN", "LEFT", "RIGHT", "IN", "OUT")


def _is_two_element_np_array(node) -> bool:
    if (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "array"
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "np"
        and node.args
        and isinstance(node.args[0], (ast.List, ast.Tuple))
    ):
        return len(node.args[0].elts) == 2
    return False


def _subtree_refs(subtree, names: set) -> bool:
    return any(
        isinstance(node, ast.Name) and node.id in names
        for node in ast.walk(subtree)
    )


def _subtree_is_2d(subtree, two_d_names: set) -> bool:
    if _subtree_refs(subtree, two_d_names):
        return True
    return any(_is_two_element_np_array(n) for n in ast.walk(subtree))


def _subtree_is_3d(subtree, three_d_names: set) -> bool:
    if _subtree_refs(subtree, three_d_names):
        return True
    for node in ast.walk(subtree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            if node.func.attr in _MANIM_3D_SOURCES:
                return True
        elif isinstance(node, ast.Name) and node.id in _MANIM_3D_CONSTANTS:
            return True
        elif (
            isinstance(node, ast.Attribute)
            and isinstance(node.value, ast.Name)
            and node.attr in ("points", "start", "end")
        ):
            return True
    return False


def _name_loads(subtree) -> set:
    loads = set()
    for node in ast.walk(subtree):
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
            if node.id != "self":
                loads.add(node.id)
    return loads


def _store_names(subtree) -> set:
    return {
        node.id
        for node in ast.walk(subtree)
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store)
    }


def _always_redraw_lambdas(stmt):
    out = []
    for node in ast.walk(stmt):
        if (
            isinstance(node, ast.Call)
            and _is_always_redraw(node)
            and node.args
        ):
            for arg in node.args:
                if isinstance(arg, ast.Lambda):
                    out.append(arg)
    return out


_EAGER_SCOPES = (ast.Lambda, ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp)


def _flatten_statements(suite):
    """Yield statements in source (execution) order, unwrapping the always-
    executed suites of compound statements (for/while/if/with/try bodies).

    Nested function/class bodies are NOT descended into: they run later in a
    different frame, so their eager scopes cannot NameError in `construct`.
    """
    for stmt in suite:
        if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            yield stmt
        elif isinstance(stmt, (ast.For, ast.AsyncFor)):
            yield stmt
            yield from _flatten_statements(stmt.body)
            yield from _flatten_statements(stmt.orelse)
        elif isinstance(stmt, ast.While):
            yield stmt
            yield from _flatten_statements(stmt.body)
            yield from _flatten_statements(stmt.orelse)
        elif isinstance(stmt, ast.If):
            yield stmt
            yield from _flatten_statements(stmt.body)
            yield from _flatten_statements(stmt.orelse)
        elif isinstance(stmt, ast.With):
            yield stmt
            yield from _flatten_statements(stmt.body)
        elif isinstance(stmt, ast.Try):
            yield stmt
            yield from _flatten_statements(stmt.body)
            for handler in stmt.handlers:
                yield from _flatten_statements(handler.body)
            yield from _flatten_statements(stmt.orelse)
            yield from _flatten_statements(stmt.finalbody)
        else:
            yield stmt


def find_closure_before_assign(code: str) -> list[str]:
    """Flag eager closures (always_redraw lambdas + comprehensions) that READ a
    local variable assigned LATER in the same function.

    always_redraw fires immediately and comprehensions run immediately where
    they appear, so reading an as-yet-unassigned local raises 'NameError: free
    variable X referenced before assignment' at render time (e.g. a listcomp
    using axes before axes = Axes()).

    Statements are walked in execution order (loop bodies unwrapped), so an
    assignment made EARLIER in the same loop iteration or block is correctly
    seen as available - only textually later reads are flagged. Loop targets
    and `with ... as` vars are bound before their suites.

    This is the plain-local twin of find_premature_self_attrs (self.X).
    """
    import builtins

    try:
        tree = ast.parse(code)
    except SyntaxError:
        return []

    builtin_names = set(dir(builtins))
    flags = []

    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef):
            continue
        params = {a.arg for a in node.args.args + node.args.kwonlyargs}
        all_locals = _store_names(node) - params - builtin_names

        seen = set(params)
        for stmt in _flatten_statements(node.body):
            if isinstance(
                stmt, (ast.For, ast.AsyncFor)
            ):
                seen |= _store_names(
                    ast.Assign(targets=[stmt.target], value=None)
                )
                continue
            if isinstance(stmt, ast.With):
                for item in stmt.items:
                    if isinstance(item.optional_vars, ast.Name):
                        seen.add(item.optional_vars.id)
                continue
            if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                seen.add(stmt.name)
                continue

            newly = _store_names(stmt) - builtin_names

            parent = {}
            for sub in ast.walk(stmt):
                for child in ast.iter_child_nodes(sub):
                    parent[id(child)] = sub

            def _comp_bound_above(scope) -> set:
                names = set()
                cur = scope
                while id(cur) in parent:
                    p = parent[id(cur)]
                    if isinstance(
                        p,
                        (ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp),
                    ):
                        for gen in p.generators:
                            names |= _store_names(
                                ast.Assign(targets=[gen.target], value=None)
                            )
                    cur = p
                return names

            eager_scopes = []
            for call in ast.walk(stmt):
                if isinstance(call, ast.Call) and _is_always_redraw(call):
                    for arg in call.args:
                        if isinstance(arg, ast.Lambda):
                            eager_scopes.append(arg)
            for sub in ast.walk(stmt):
                if isinstance(sub, _EAGER_SCOPES) and sub not in eager_scopes:
                    eager_scopes.append(sub)

            for scope in eager_scopes:
                own = set()
                if isinstance(scope, ast.Lambda):
                    own = {a.arg for a in scope.args.args}
                own |= _store_names(scope)
                own |= _comp_bound_above(scope)
                for name in _name_loads(scope) - own - builtin_names:
                    if name in all_locals and name not in seen:
                        flags.append(
                            f"line {scope.lineno}: reads '{name}' before it is assigned"
                        )
            seen |= newly

    return sorted(set(flags))


def find_2d_3d_broadcast(code: str) -> list[str]:
    """Flag 2D numpy array (np.array([x, y])) added/subtracted to a Manim 3D
    point, which crashes the render with 'operands could not be broadcast
    together with shapes (3,) (2,)'.

    This is a taint-lite heuristic: names bound from a two-element np.array
    literal are 2D; names bound from coords_to_point/get_center/etc. or the
    ORIGIN/UP/DOWN/... constants are 3D. A +/- mixing them is a bug.
    """
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return []

    two_d_names = set()
    three_d_names = set()

    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets:
            if not isinstance(target, ast.Name):
                continue
            if _subtree_is_2d(node.value, two_d_names):
                two_d_names.add(target.id)
            if _subtree_is_3d(node.value, three_d_names):
                three_d_names.add(target.id)

    flags = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.BinOp) or not isinstance(
            node.op, (ast.Add, ast.Sub)
        ):
            continue
        left_2d = _subtree_is_2d(node.left, two_d_names)
        left_3d = _subtree_is_3d(node.left, three_d_names)
        right_2d = _subtree_is_2d(node.right, two_d_names)
        right_3d = _subtree_is_3d(node.right, three_d_names)
        if (left_2d and right_3d) or (right_2d and left_3d):
            expr = ast.get_source_segment(code, node) or ast.dump(node)
            flags.append(f"line {node.lineno}: {expr}")

    return flags


_LOOP_HEAVY_CONSTRUCTS = (
    "Tex", "MathTex", "Arrow", "CurvedArrow", "VMobject", "Dot",
    "LabeledDot", "VGroup", "Group",
)


def _manim_classes() -> dict:
    """Map every Manim CE class name to the class object."""
    return {
        name: getattr(manim, name)
        for name in dir(manim)
        if isinstance(getattr(manim, name), type)
    }


_INSTANCE_ONLY_VMOBJECT_METHODS = {
    "set_flat_shading",
    "set_gloss",
}


def find_unknown_methods(code: str) -> list[str]:
    """Flag attribute-method calls that do not exist on the receiver's class.

    find_unknown_symbols only checks bare names, so hallucinated METHODS slip
    through (e.g. `traj.set_points_smooth(...)` - the real API is
    `set_points_smoothly`). When construct() raises, Manim's error-page render
    hangs until the 120s timeout, wasting the whole attempt.

    Some real Manim methods live only on instances, not on the class
    (Mobject.__getattr__ synthesizes them), so a small allowlist keeps them
    legal: set_flat_shading / set_gloss disable Manim's default surface
    lighting and are key for truthful 3D colors.

    Type inference is deliberately shallow: only `name = ManimClass(...)` binds
    a known receiver type. Unknown receivers (params, numpy arrays, call-chain
    results) are left alone to avoid false positives.
    """
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return []

    classes = _manim_classes()
    var_types = {}

    def _bind(target, cls) -> None:
        if isinstance(target, ast.Name):
            var_types[target.id] = cls
        elif isinstance(target, (ast.Tuple, ast.List)):
            for elt in target.elts:
                _bind(elt, cls)

    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        cls = None
        if isinstance(node.value, ast.Call):
            func = node.value.func
            if isinstance(func, ast.Name) and func.id in classes:
                cls = classes[func.id]
            elif isinstance(func, ast.Attribute) and func.attr in classes:
                cls = classes[func.attr]
        if cls is not None:
            for target in node.targets:
                _bind(target, cls)

    self_ok = set(_class_methods(tree))
    base_resolved = False
    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef):
            continue
        for base in node.bases:
            if isinstance(base, ast.Name) and base.id in classes:
                self_ok |= set(dir(classes[base.id]))
                base_resolved = True
    if not base_resolved:
        self_ok |= set(dir(manim.Scene))
    flags = []

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
            continue
        receiver = node.func.value
        if isinstance(receiver, ast.Name) and receiver.id in var_types:
            cls = var_types[receiver.id]
            if (
                node.func.attr not in dir(cls)
                and node.func.attr not in _INSTANCE_ONLY_VMOBJECT_METHODS
            ):
                flags.append(
                    f"line {node.lineno}: '{node.func.attr}' is not a method of "
                    f"{cls.__name__} ({receiver.id} is a {cls.__name__}). Use "
                    f"only methods that exist on {cls.__name__}."
                )
        elif isinstance(receiver, ast.Name) and receiver.id == "self":
            if node.func.attr not in self_ok:
                flags.append(
                    f"line {node.lineno}: 'self.{node.func.attr}' is not a "
                    "method or attribute on a Manim Scene."
                )

    return flags


def _is_self_play_call(node) -> bool:
    return (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "self"
        and node.func.attr == "play"
    )


def _constructs_heavy_mobject(node) -> bool:
    if not isinstance(node, ast.Call):
        return False
    func = node.func
    if isinstance(func, ast.Name):
        return func.id in _LOOP_HEAVY_CONSTRUCTS
    if isinstance(func, ast.Attribute):
        return func.attr in _LOOP_HEAVY_CONSTRUCTS
    return False


def _is_small_literal_bound(iter_node) -> bool:
    """True if the loop provably iterates at most 2 times from literals.

    range(...) counts only when every argument is an integer literal
    (range(len(points)) is unresolvable -> not small). Literal lists /
    tuples / sets count by length; a plain `while` is never small.
    """
    if isinstance(iter_node, (ast.List, ast.Tuple, ast.Set)):
        return len(iter_node.elts) <= 2
    if isinstance(iter_node, ast.Constant):
        return isinstance(iter_node.value, str) and len(iter_node.value) <= 2
    if (
        isinstance(iter_node, ast.Call)
        and isinstance(iter_node.func, ast.Name)
        and iter_node.func.id == "range"
    ):
        consts = [
            arg.value
            for arg in iter_node.args
            if isinstance(arg, ast.Constant) and isinstance(arg.value, int)
        ]
        if len(consts) != len(iter_node.args):
            return False
        try:
            return len(list(range(*consts))) <= 2
        except (TypeError, ValueError):
            return False
    return False


def find_loop_play_risks(code: str) -> list[str]:
    """Flag for/while loops that risk the 120s render timeout.

    Only PER-FRAME rendering is the actual timeout driver, so a loop is
    flagged when it is not provably bounded (<= 2 literal iterations) and:
      - its body calls self.play(), or
      - its body rebuilds heavy mobjects (Tex/MathTex/Arrow/VMobject/Dot/
        VGroup) inside an always_redraw callback (rebuilt every frame).

    One-time BATCH construction inside a loop (no self.play, no always_redraw)
    is cheap and NOT flagged - e.g. building 14 arrows once before animating
    them. Bias hard toward blocking per-frame patterns: a false positive costs
    one cheap repair round-trip, a false negative costs a 120-second render
    and a whole attempt.
    """
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return []

    flags = []

    for node in ast.walk(tree):
        if isinstance(node, ast.While):
            bounded = False
            kind = "while"
            iter_desc = "while"
        elif isinstance(node, ast.For):
            bounded = _is_small_literal_bound(node.iter)
            kind = "for"
            iter_desc = ast.get_source_segment(code, node.iter) or ast.dump(node.iter)
        else:
            continue

        if bounded:
            continue

        play_lines = []
        heavy_lines = []
        redraw_present = False
        for stmt in node.body + node.orelse:
            for sub in ast.walk(stmt):
                if _is_self_play_call(sub):
                    play_lines.append(sub.lineno)
                elif _constructs_heavy_mobject(sub):
                    heavy_lines.append(sub.lineno)
                if isinstance(sub, ast.Call) and _is_always_redraw(sub):
                    redraw_present = True

        reasons = []
        if play_lines:
            reasons.append(f"calls self.play() on lines {sorted(set(play_lines))}")
        if heavy_lines and redraw_present:
            reasons.append(
                f"rebuilds heavy mobjects inside always_redraw on lines "
                f"{sorted(set(heavy_lines))}"
            )
        if not reasons:
            continue

        flags.append(
            f"line {node.lineno}: {kind} loop over '{iter_desc}' "
            + "; ".join(reasons)
            + " - running this per-iteration can exceed the render timeout. "
            "Precompute the full path into a VMobject BEFORE the animation and "
            "animate ONCE with MoveAlongPath; use at most 2 always_redraw "
            "mobjects for anything that must track the motion. Never call "
            "self.play() inside a loop."
        )

    return flags


if __name__ == "__main__":
    BAD_UNDEFINED = '''
from manim import *

class GeneratedScene(Scene):
    def construct(self):
        ball = Dot().move_to(LEFT * 2)
        ball.add_updater(
            lambda m: m.set_opacity(self.current_velocity / 5)
        )
        self.play(Create(ball))
        self.wait()
'''
    BAD_PREMATURE = '''
from manim import *

class GeneratedScene(Scene):
    def get_arrow(self, t):
        return Arrow(ORIGIN, UP * t)

    def construct(self):
        arrow = always_redraw(
            lambda: self.get_arrow(self.anim_time)
        )
        self.anim_time = 0
        self.play(Create(arrow))
        self.wait()
'''
    BAD_READONLY = '''
from manim import *

class GeneratedScene(Scene):
    def construct(self):
        self.time = 0
        self.wait()
'''
    BAD_BROADCAST = '''
from manim import *

class GeneratedScene(Scene):
    def construct(self):
        axes = Axes()
        point = axes.coords_to_point(1, 2)
        vx, vy = 3.0, 4.0
        dir_vec = np.array([vx, vy])
        arrow_end = point + dir_vec * 0.8
        self.play(Create(Arrow(point, arrow_end)))
'''
    GOOD_BROADCAST = '''
from manim import *

class GeneratedScene(Scene):
    def construct(self):
        axes = Axes()
        point = axes.coords_to_point(1, 2)
        vx, vy = 3.0, 4.0
        dir_vec = np.array([vx, vy, 0])
        arrow_end = point + dir_vec * 0.8
        self.play(Create(Arrow(point, arrow_end)))
'''
    BAD_CLOSURE = '''
from manim import *

class GeneratedScene(Scene):
    def construct(self):
        arrow = always_redraw(lambda: Arrow(axes.get_center(), ORIGIN))
        axes = Axes()
        self.play(Create(arrow), Create(axes))
'''
    BAD_COMPREHENSION = '''
from manim import *

class GeneratedScene(Scene):
    def construct(self):
        xs = np.linspace(0, 1, 20)
        points = [axes.c2p(x, x * x) for x in xs]
        axes = Axes()
        self.play(Create(Line(points[0], points[-1])), Create(axes))
'''
    GOOD_CLOSURE = '''
from manim import *

class GeneratedScene(Scene):
    def construct(self):
        axes = Axes()
        arrow = always_redraw(lambda: Arrow(axes.get_center(), ORIGIN))
        self.play(Create(arrow), Create(axes))
'''
    GOOD = '''
from manim import *

class GeneratedScene(Scene):
    def construct(self):
        self.current_velocity = 3.0
        ball = Dot().move_to(LEFT * 2)
        ball.add_updater(
            lambda m: m.set_opacity(self.current_velocity / 5)
        )
        self.play(Create(ball))
        self.wait()
'''
    BASE = '''
from manim import *

class GeneratedScene(Scene):
    def construct(self):
        text = Text("hi").to_edge(UP)
        self.play(Write(text))
        self.wait()
'''
    BAD_LOOP = '''
from manim import *

class GeneratedScene(Scene):
    def construct(self):
        n_steps = 60
        ball = Dot(ORIGIN)
        for i in range(1, n_steps):
            pos = ORIGIN + UP * i * 0.01
            self.play(ball.animate.move_to(pos), run_time=0.08)
'''
    BAD_LOOP_TEX = '''
from manim import *

class GeneratedScene(Scene):
    def construct(self):
        for t in np.linspace(0, 1, 20):
            label = always_redraw(lambda: MathTex("x"))
            self.add(label)
'''
    BAD_WHILE = '''
from manim import *

class GeneratedScene(Scene):
    def construct(self):
        t = 0.0
        ball = Dot(ORIGIN)
        while t < 10:
            self.play(ball.animate.shift(UP * 0.01))
            t += 0.1
'''
    BAD_LOOP_ARROW = '''
from manim import *

class GeneratedScene(Scene):
    def construct(self):
        arrow = Arrow(ORIGIN, UP)
        for i in range(n):
            self.play(Transform(arrow, Arrow(ORIGIN, UP * i)))
'''
    GOOD_BATCH_ARROW = '''
from manim import *

class GeneratedScene(Scene):
    def construct(self):
        arrows = []
        for i in range(10):
            arrows.append(Arrow(ORIGIN, UP * i))
        self.play(Create(VGroup(*arrows)))
'''
    GOOD_LOOP_2 = '''
from manim import *

class GeneratedScene(Scene):
    def construct(self):
        ball = Dot(ORIGIN)
        for i in range(2):
            self.play(ball.animate.shift(UP))
'''
    GOOD_LOOP_2_TEX = '''
from manim import *

class GeneratedScene(Scene):
    def construct(self):
        labels = []
        for i in range(2):
            labels.append(MathTex("x"))
        self.play(Write(VGroup(*labels)))
'''
    GOOD_LOOP_PRECOMPUTE = '''
from manim import *

class GeneratedScene(Scene):
    def construct(self):
        n_steps = 60
        points = []
        for i in range(n_steps):
            points.append(ORIGIN + UP * i * 0.01)
        path = VMobject()
        path.set_points_smoothly(points)
        self.play(MoveAlongPath(Dot(), path))
'''
    BAD_METHOD = '''
from manim import *

class GeneratedScene(Scene):
    def construct(self):
        traj = VMobject()
        traj.set_points_smooth([ORIGIN, UP])
        self.play(Create(traj))
'''
    GOOD_METHOD = '''
from manim import *

class GeneratedScene(Scene):
    def construct(self):
        traj = VMobject()
        traj.set_points_smoothly([ORIGIN, UP])
        self.play(Create(traj))
'''
    BAD_SELF_METHOD = '''
from manim import *

class GeneratedScene(Scene):
    def construct(self):
        self.set_camera_orientation(phi=0)
'''
    GOOD_SELF_METHOD = '''
from manim import *

class GeneratedScene(Scene):
    def get_ball(self):
        return Dot()

    def construct(self):
        ball = self.get_ball()
        ball.move_to(UP)
        self.play(Create(ball))
        self.wait(1)
'''
    assert find_undefined_self_attrs(BAD_UNDEFINED) == ["current_velocity"], find_undefined_self_attrs(BAD_UNDEFINED)
    assert find_undefined_self_attrs(GOOD) == [], find_undefined_self_attrs(GOOD)
    assert find_undefined_self_attrs(BASE) == [], find_undefined_self_attrs(BASE)
    assert find_premature_self_attrs(BAD_PREMATURE) == ["anim_time"], find_premature_self_attrs(BAD_PREMATURE)
    assert find_premature_self_attrs(GOOD) == [], find_premature_self_attrs(GOOD)
    assert find_premature_self_attrs(BASE) == [], find_premature_self_attrs(BASE)
    assert find_readonly_self_assignments(BAD_READONLY) == ["time"], find_readonly_self_assignments(BAD_READONLY)
    assert find_readonly_self_assignments(BASE) == [], find_readonly_self_assignments(BASE)
    assert len(find_2d_3d_broadcast(BAD_BROADCAST)) == 1, find_2d_3d_broadcast(BAD_BROADCAST)
    assert find_2d_3d_broadcast(GOOD_BROADCAST) == [], find_2d_3d_broadcast(GOOD_BROADCAST)
    assert find_2d_3d_broadcast(BASE) == [], find_2d_3d_broadcast(BASE)
    assert len(find_closure_before_assign(BAD_CLOSURE)) == 1, find_closure_before_assign(BAD_CLOSURE)
    assert len(find_closure_before_assign(BAD_COMPREHENSION)) == 1, find_closure_before_assign(BAD_COMPREHENSION)
    assert find_closure_before_assign(GOOD_CLOSURE) == [], find_closure_before_assign(GOOD_CLOSURE)
    assert find_closure_before_assign(BASE) == [], find_closure_before_assign(BASE)
    assert len(find_loop_play_risks(BAD_LOOP)) == 1, find_loop_play_risks(BAD_LOOP)
    assert len(find_loop_play_risks(BAD_LOOP_TEX)) == 1, find_loop_play_risks(BAD_LOOP_TEX)
    assert len(find_loop_play_risks(BAD_WHILE)) == 1, find_loop_play_risks(BAD_WHILE)
    assert len(find_loop_play_risks(BAD_LOOP_ARROW)) == 1, find_loop_play_risks(BAD_LOOP_ARROW)
    assert find_loop_play_risks(GOOD_LOOP_2) == [], find_loop_play_risks(GOOD_LOOP_2)
    assert find_loop_play_risks(GOOD_LOOP_2_TEX) == [], find_loop_play_risks(GOOD_LOOP_2_TEX)
    assert find_loop_play_risks(GOOD_LOOP_PRECOMPUTE) == [], find_loop_play_risks(GOOD_LOOP_PRECOMPUTE)
    assert find_loop_play_risks(GOOD_BATCH_ARROW) == [], find_loop_play_risks(GOOD_BATCH_ARROW)
    assert find_loop_play_risks(BASE) == [], find_loop_play_risks(BASE)
    assert len(find_unknown_methods(BAD_METHOD)) == 1, find_unknown_methods(BAD_METHOD)
    assert find_unknown_methods(GOOD_METHOD) == [], find_unknown_methods(GOOD_METHOD)
    assert len(find_unknown_methods(BAD_SELF_METHOD)) == 1, find_unknown_methods(BAD_SELF_METHOD)
    assert find_unknown_methods(GOOD_SELF_METHOD) == [], find_unknown_methods(GOOD_SELF_METHOD)
    assert find_unknown_methods(BASE) == [], find_unknown_methods(BASE)
    print("static_checks self-test OK")
