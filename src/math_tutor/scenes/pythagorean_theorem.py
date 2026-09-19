from manim import (
    BLUE,
    DOWN,
    GREEN,
    RED,
    RIGHT,
    UP,
    Create,
    FadeIn,
    MathTex,
    Polygon,
    Scene,
    VGroup,
)


class PythagoreanTheorem(Scene):
    def construct(self) -> None:
        triangle = Polygon(
            [-3, -1.5, 0],
            [1, -1.5, 0],
            [1, 1.5, 0],
            color=BLUE,
        )
        labels = VGroup(
            MathTex("a", color=GREEN).next_to(triangle, direction=DOWN),
            MathTex("b", color=GREEN).next_to(triangle, direction=RIGHT),
            MathTex("c", color=RED).move_to([-1.2, 0.25, 0]),
        )
        equation = MathTex("a^2 + b^2 = c^2").to_edge(UP)

        self.play(Create(triangle), FadeIn(labels))
        self.play(FadeIn(equation))
        self.wait(1)
