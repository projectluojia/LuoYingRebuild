from __future__ import annotations

import json
from typing import Any

import httpx

from luoying_bot.capabilities.knowledge_base.errors import BackendUnavailable
from luoying_bot.capabilities.knowledge_base.ports import StructuredBackend


class DirectusClient(StructuredBackend):
    def __init__(
        self,
        *,
        base_url: str,
        token: str,
        timeout_sec: float = 20.0,
        client: httpx.AsyncClient | None = None,
    ):
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.timeout_sec = timeout_sec
        self.client = client

    @property
    def configured(self) -> bool:
        return bool(self.base_url and self.token)

    async def list_items(
        self,
        collection: str,
        *,
        filters: dict[str, Any],
        fields: list[str] | None = None,
        limit: int = 20,
        sort: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        if not self.configured:
            raise BackendUnavailable("Directus 未配置")
        params: dict[str, Any] = {
            "limit": str(limit),
            "filter": json.dumps(filters, ensure_ascii=False),
        }
        if fields:
            params["fields"] = ",".join(fields)
        if sort:
            params["sort"] = ",".join(sort)

        data = await self._request("GET", f"/items/{collection}", params=params)
        items = data.get("data", [])
        return [dict(item) for item in items if isinstance(item, dict)]

    async def create_item(
        self,
        collection: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        if not self.configured:
            raise BackendUnavailable("Directus 未配置")
        data = await self._request("POST", f"/items/{collection}", json_body=payload)
        item = data.get("data", {})
        return dict(item) if isinstance(item, dict) else {}

    async def update_item(
        self,
        collection: str,
        item_id: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        if not self.configured:
            raise BackendUnavailable("Directus 未配置")
        data = await self._request("PATCH", f"/items/{collection}/{item_id}", json_body=payload)
        item = data.get("data", {})
        return dict(item) if isinstance(item, dict) else {}

    async def list_collections(self) -> set[str]:
        if not self.configured:
            raise BackendUnavailable("Directus 未配置")
        data = await self._request("GET", "/collections")
        result: set[str] = set()
        for item in data.get("data", []):
            if isinstance(item, dict) and item.get("collection"):
                result.add(str(item["collection"]))
        return result

    async def create_collection(self, collection: str, *, note: str = "") -> dict[str, Any]:
        if not self.configured:
            raise BackendUnavailable("Directus 未配置")
        return await self._request(
            "POST",
            "/collections",
            json_body={
                "collection": collection,
                "meta": {
                    "collection": collection,
                    "note": note,
                    "hidden": False,
                },
                "schema": {},
            },
        )

    async def list_fields(self, collection: str) -> set[str]:
        if not self.configured:
            raise BackendUnavailable("Directus 未配置")
        data = await self._request("GET", f"/fields/{collection}")
        result: set[str] = set()
        for item in data.get("data", []):
            if isinstance(item, dict) and item.get("field"):
                result.add(str(item["field"]))
        return result

    async def create_field(
        self,
        collection: str,
        field: str,
        *,
        field_type: str,
        interface: str | None = None,
        note: str = "",
        required: bool = False,
        default_value: Any = None,
    ) -> dict[str, Any]:
        if not self.configured:
            raise BackendUnavailable("Directus 未配置")
        schema: dict[str, Any] = {}
        if default_value is not None:
            schema["default_value"] = default_value
        return await self._request(
            "POST",
            f"/fields/{collection}",
            json_body={
                "field": field,
                "type": field_type,
                "meta": {
                    "interface": interface or self._default_interface(field_type),
                    "note": note,
                    "required": required,
                },
                "schema": schema,
            },
        )

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json_body: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        headers = {"Authorization": f"Bearer {self.token}"}
        if self.client is not None:
            response = await self.client.request(
                method,
                f"{self.base_url}{path}",
                params=params,
                json=json_body,
                headers=headers,
            )
        else:
            async with httpx.AsyncClient(timeout=self.timeout_sec) as client:
                response = await client.request(
                    method,
                    f"{self.base_url}{path}",
                    params=params,
                    json=json_body,
                    headers=headers,
                )
        if response.status_code >= 400:
            raise BackendUnavailable(
                f"Directus 请求失败：{response.status_code} {response.text[:300]}"
            )
        payload = response.json()
        return dict(payload) if isinstance(payload, dict) else {}

    def _default_interface(self, field_type: str) -> str:
        return {
            "text": "input-multiline",
            "json": "input-code",
            "datetime": "datetime",
            "integer": "input",
            "float": "input",
            "boolean": "boolean",
        }.get(field_type, "input")
