from __future__ import annotations


class KnowledgeBaseError(RuntimeError):
    pass


class BackendUnavailable(KnowledgeBaseError):
    pass


class NoReliableSource(KnowledgeBaseError):
    pass


class KnowledgePermissionDenied(KnowledgeBaseError):
    pass

