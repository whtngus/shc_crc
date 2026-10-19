"""워크플로우 W-1 단계 흐름을 LangGraph StateGraph로 구현함(설계서 6 ~ 7장 흐름 도식)."""

from __future__ import annotations

from langgraph.graph import END, START, StateGraph

from ..application.models import WorkflowState
from ..application.ports import WorkflowRunnerPort
from ..application.steps import WorkflowSteps, next_after_r3, next_after_r4
from ..domain import time_budget as tb

# 정상 최대 방문 수는 9회(S-R1, S-R2 ~ S-R4 두 바퀴, S-R5, S-R6). 반복 상한은 attempt가 맡고,
# 혹시 모를 무한 반복은 이 값이 한 번 더 막음(GraphRecursionError → 서비스가 INTERNAL_ERROR로 바꿈)
RECURSION_LIMIT = 12


class LangGraphRunner(WorkflowRunnerPort):
    """WorkflowRunnerPort 구현체. 노드는 단계 6개, 조건 간선은 S-R3 뒤와 S-R4 뒤 2개임.

    오류 종료는 단계 함수가 던지는 RetrieverError가 그래프를 멈추는 방식으로 처리함.
    체크포인트는 두지 않음(설계서 재개 방안 "해당없음").
    """

    def __init__(self, steps: WorkflowSteps):
        builder = StateGraph(WorkflowState)
        builder.add_node(tb.STAGE_R1, steps.step_r1)
        builder.add_node(tb.STAGE_R2, steps.step_r2)
        builder.add_node(tb.STAGE_R3, steps.step_r3)
        builder.add_node(tb.STAGE_R4, steps.step_r4)
        builder.add_node(tb.STAGE_R5, steps.step_r5)
        builder.add_node(tb.STAGE_R6, steps.step_r6)

        builder.add_edge(START, tb.STAGE_R1)
        builder.add_edge(tb.STAGE_R1, tb.STAGE_R2)
        builder.add_edge(tb.STAGE_R2, tb.STAGE_R3)
        # S-R3: 적합 → S-R4, 부적합(재시도 남음) → S-R2, 답할 수 없음 → S-R6
        builder.add_conditional_edges(
            tb.STAGE_R3, next_after_r3, [tb.STAGE_R4, tb.STAGE_R2, tb.STAGE_R6]
        )
        # S-R4: 통과 → S-R5, 실패(재시도 남음) → S-R2. 재시도 소진은 단계 안에서 오류 종료
        builder.add_conditional_edges(tb.STAGE_R4, next_after_r4, [tb.STAGE_R5, tb.STAGE_R2])
        builder.add_edge(tb.STAGE_R5, tb.STAGE_R6)
        builder.add_edge(tb.STAGE_R6, END)
        self._graph = builder.compile()

    def run(self, initial_state: WorkflowState) -> WorkflowState:
        """트리거 입력으로 S-R1부터 S-R6까지 실행하고 최종 상태를 돌려줌."""
        return self._graph.invoke(initial_state, config={"recursion_limit": RECURSION_LIMIT})

    def mermaid(self) -> str:
        """컴파일된 그래프를 Mermaid 문장으로 돌려줌. 설계서 도식과 연결을 대조할 때 씀."""
        return self._graph.get_graph().draw_mermaid()
