from dataclasses import dataclass
import os
from typing import Any

from apps.api_gateway.services.run_dispatcher import RunDispatcher
from packages.dbos_workflows.service import DBOSWorkflowService
from packages.events.bus import EventBus, FailOpenEventBus, InMemoryEventBus, RedisStreamsEventBus
from packages.context.prefill import AgentContextPrefill, load_agent_context_prefill
from packages.context.cache import ContextProviderCache
from packages.memory.service import MemoryService
from packages.rag.config import (
    build_rag_embedding_encoder,
    build_rag_reranker,
    load_rag_reranker_config,
)
from packages.rag.postgres import PostgresRagRepository
from packages.rag.search import EmptyTestRagSearchService, HybridRagSearchService
from packages.model.router import ModelRouter
from packages.observability.langfuse_sink import LangfuseRuntimeSink
from packages.observations.service import ObservationService
from packages.plugins.station_api import build_station_api_tool_adapter
from packages.plugins.version_router import PluginVersionRouter
from packages.plugins.supervisor import PluginProcessSupervisor
from packages.security.auth import Hs256JwtVerifier
from packages.security.rate_limit import InMemoryRateLimiter
from packages.security.tool_gateway import ToolGatewayGuard
from packages.session_search.base import ResourceSearch
from packages.session_search.memory import InMemoryResourceSearch
from packages.session_search.postgres import PostgresResourceSearch
from packages.skills.meta_tools import SkillMetaTools
from packages.skills.lifecycle_service import SkillLifecycleService
from packages.skills.registry import SkillRegistry
from packages.reflection.repositories import (
    LearningCandidateRepository,
    ReflectionJobRepository,
)
from packages.reflection.service import ReflectionService
from packages.storage.repositories.evidence import EvidenceRepository
from packages.storage.repositories.observations import ObservationRepository
from packages.storage.repositories.plugins import PluginRepository
from packages.storage.repositories.runs import RunRepository
from packages.storage.repositories.traces import TraceRepository
from packages.storage.db import InMemoryDatabase
from packages.storage.repositories.memories import MemoryRepository
from packages.storage.repositories.skills import SkillRepository
from packages.storage.postgres_connection import build_postgres_connection_factory, ensure_repository_schema
from packages.storage.postgres_memory_repository import PostgresMemoryRepository
from packages.storage.postgres_learning_repository import (
    PostgresLearningCandidateRepository,
    PostgresReflectionJobRepository,
)
from packages.storage.postgres_skill_repository import PostgresSkillRepository
from packages.storage.postgres_repository import (
    PostgresEvidenceRepository,
    PostgresObservationRepository,
    PostgresPluginRepository,
    PostgresRunRepository,
    PostgresTraceRepository,
)
from packages.tool_registry.registry import CapabilityRegistry
from packages.wal.service import InMemoryWriteAheadLog, PostgresWriteAheadLog, WriteAheadLog
from packages.workflow.durable import DbosDurableWorkflowAdapter


@dataclass
class AppContainer:
    runs: RunRepository
    traces: TraceRepository
    evidence: EvidenceRepository
    observations: ObservationRepository
    plugins: PluginRepository
    event_bus: EventBus
    rpc_wal: WriteAheadLog
    state_wal: WriteAheadLog
    durable_workflows: DbosDurableWorkflowAdapter
    run_dispatcher: RunDispatcher
    memory_service: MemoryService
    rag_search_service: Any | None
    skill_meta_tools: SkillMetaTools
    reflection_service: ReflectionService
    plugin_version_router: PluginVersionRouter
    plugin_process_supervisor: PluginProcessSupervisor
    observation_service: ObservationService
    tool_guard: ToolGatewayGuard
    model_router: ModelRouter
    session_search: ResourceSearch
    agent_context_prefill: AgentContextPrefill
    context_provider_cache: ContextProviderCache
    langfuse_runtime_sink: LangfuseRuntimeSink
    capability_registry: CapabilityRegistry
    station_api_client: Any | None


def build_event_bus(redis_client: Any | None = None) -> EventBus:
    """本地保持内存事件流；Docker 配置 Redis 时启用可恢复 Streams。"""
    if not os.getenv("REDIS_URL"):
        return InMemoryEventBus()
    if redis_client is None:
        import redis

        redis_client = redis.Redis.from_url(os.environ["REDIS_URL"], decode_responses=True)
    return FailOpenEventBus(primary=RedisStreamsEventBus(redis_client))


def build_container() -> AppContainer:
    database_url = os.getenv("DATABASE_URL")
    rag_search_service: HybridRagSearchService | None = None
    if database_url:
        connection_factory = build_postgres_connection_factory(database_url)
        ensure_repository_schema(connection_factory)
        session_search = PostgresResourceSearch(connection_factory)
        runs = PostgresRunRepository(connection_factory)
        traces = PostgresTraceRepository(connection_factory)
        evidence = PostgresEvidenceRepository(connection_factory)
        observations = PostgresObservationRepository(connection_factory)
        plugins = PostgresPluginRepository(connection_factory)
        memory_repo = PostgresMemoryRepository(connection_factory)
        if os.getenv("AGENT_HARNESS_RAG_ENABLED", "false").lower() == "true":
            reranker = None
            reranker_config = load_rag_reranker_config()
            if os.getenv(
                "AGENT_HARNESS_RAG_RERANKER_ENABLED", "false"
            ).lower() == "true":
                reranker = build_rag_reranker(reranker_config)
            rag_search_service = HybridRagSearchService(
                PostgresRagRepository(connection_factory),
                build_rag_embedding_encoder(),
                reranker=reranker,
                rerank_candidate_k=reranker_config.candidate_k,
            )
        skill_repo = PostgresSkillRepository(connection_factory)
        reflection_jobs = PostgresReflectionJobRepository(connection_factory)
        learning_candidates = PostgresLearningCandidateRepository(connection_factory)
        rpc_wal = PostgresWriteAheadLog(connection_factory)
        state_wal = PostgresWriteAheadLog(connection_factory)
    else:
        learning_db = InMemoryDatabase()
        session_search = InMemoryResourceSearch()
        runs = RunRepository()
        traces = TraceRepository(session_search=session_search)
        evidence = EvidenceRepository()
        observations = ObservationRepository()
        plugins = PluginRepository()
        memory_repo = MemoryRepository(learning_db)
        skill_repo = SkillRepository(learning_db)
        reflection_jobs = ReflectionJobRepository(learning_db)
        learning_candidates = LearningCandidateRepository(learning_db)
        rpc_wal = InMemoryWriteAheadLog()
        state_wal = InMemoryWriteAheadLog()
        if os.getenv("AGENT_HARNESS_PROFILE") == "test":
            rag_search_service = EmptyTestRagSearchService()
    event_bus = build_event_bus()
    durable_workflows = DbosDurableWorkflowAdapter(DBOSWorkflowService())
    observation_service = ObservationService(
        evidence_repo=evidence,
        observation_repo=observations,
        event_bus=event_bus,
    )
    run_dispatcher = RunDispatcher(
        runs=runs,
        traces=traces,
        durable_workflows=durable_workflows,
        event_bus=event_bus,
        state_wal=state_wal,
    )
    station_api_adapter = build_station_api_tool_adapter()
    memory_service = MemoryService(repo=memory_repo)
    skill_meta_tools = SkillMetaTools(
        SkillLifecycleService(
            SkillRegistry(skill_repo),
            auto_promote_low_risk=(
                os.getenv("AGENT_HARNESS_AUTO_PROMOTE_LOW_RISK_SKILLS", "false").lower()
                == "true"
            ),
        )
    )
    reflection_service = ReflectionService(
        jobs=reflection_jobs,
        candidates=learning_candidates,
        traces=traces,
        memory_service=memory_service,
        skill_meta_tools=skill_meta_tools,
        event_bus=event_bus,
        evidence_repo=evidence,
    )
    plugin_process_supervisor = PluginProcessSupervisor()
    return AppContainer(
        runs=runs,
        traces=traces,
        evidence=evidence,
        observations=observations,
        plugins=plugins,
        event_bus=event_bus,
        rpc_wal=rpc_wal,
        state_wal=state_wal,
        durable_workflows=durable_workflows,
        run_dispatcher=run_dispatcher,
        memory_service=memory_service,
        rag_search_service=rag_search_service,
        skill_meta_tools=skill_meta_tools,
        reflection_service=reflection_service,
        plugin_version_router=PluginVersionRouter(),
        plugin_process_supervisor=plugin_process_supervisor,
        observation_service=observation_service,
        tool_guard=ToolGatewayGuard(Hs256JwtVerifier(), InMemoryRateLimiter()),
        model_router=ModelRouter.from_config(),
        session_search=session_search,
        agent_context_prefill=load_agent_context_prefill(),
        context_provider_cache=ContextProviderCache(
            ttl_seconds=int(os.getenv("AGENT_HARNESS_CONTEXT_CACHE_TTL", "15"))
        ),
        langfuse_runtime_sink=LangfuseRuntimeSink(),
        capability_registry=CapabilityRegistry.from_builtin_manifests(),
        station_api_client=station_api_adapter.client if station_api_adapter else None,
    )


container = build_container()


def get_container() -> AppContainer:
    return container


async def get_container_dependency() -> AppContainer:
    return container
