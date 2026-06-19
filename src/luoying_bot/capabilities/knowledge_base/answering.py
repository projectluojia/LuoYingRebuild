from __future__ import annotations

from luoying_bot.capabilities.knowledge_base.models import KnowledgeAnswer, KnowledgeQuery, RetrievalResult
from luoying_bot.capabilities.knowledge_base.prompts import ANSWER_PROMPT
from luoying_bot.ports.llm import ChatModel


class KnowledgeAnswerGenerator:
    def __init__(self, model: ChatModel | None):
        self.model = model

    async def generate(self, query: KnowledgeQuery, retrieval: RetrievalResult) -> KnowledgeAnswer:
        citations = retrieval.citations()
        structured_context = "\n".join(
            f"- {record.text()}" for record in retrieval.structured_records[:30]
        ) or "无"
        rag_context = "\n".join(
            f"- {chunk.text}" for chunk in retrieval.chunks[:8] if chunk.text.strip()
        ) or "无"

        if self.model is None:
            answer = self._render_answer_without_model(structured_context, rag_context)
        else:
            prompt = ANSWER_PROMPT.format(
                question=query.question,
                structured_context=structured_context,
                rag_context=rag_context,
            )
            answer = await self.model.chat(
                [
                    {"role": "system", "content": "你只依据用户提供的知识库资料回答。"},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.2,
            )
            answer = self._strip_agent_json(answer)

        confidence = 0.85 if retrieval.structured_records else 0.72
        if retrieval.structured_records and retrieval.chunks:
            confidence = 0.9
        return KnowledgeAnswer(
            answer=answer.strip(),
            citations=citations,
            confidence=confidence,
            data={
                "structured_records": [record.to_dict() for record in retrieval.structured_records],
                "chunks": [chunk.to_dict() for chunk in retrieval.chunks],
            },
        )

    def _render_answer_without_model(self, structured_context: str, rag_context: str) -> str:
        if structured_context != "无":
            return f"根据当前结构化资料：\n{structured_context}"
        return f"根据当前文档资料：\n{rag_context}"

    def _strip_agent_json(self, text: str) -> str:
        raw = text.strip()
        if raw.startswith("{") and '"answer"' in raw:
            import json

            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                return raw
            answer = data.get("answer")
            if isinstance(answer, str) and answer.strip():
                return answer.strip()
        return raw
