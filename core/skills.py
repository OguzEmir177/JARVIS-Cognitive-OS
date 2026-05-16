import logging
from typing import Dict, Any, List, Callable, Optional
from dataclasses import dataclass, field

logger = logging.getLogger("JARVIS.SkillSystem")

@dataclass
class Skill:
    name: str
    description: str
    input_schema: Dict[str, Any]
    output_schema: Dict[str, Any]
    executor: Optional[Callable] = None
    protocol_tag: str = ""
    confidence: float = 1.0
    dependencies: List[str] = field(default_factory=list)
    execution_cost: int = 1  # 1=fast, 5=slow
    retry_policy: Dict[str, Any] = field(default_factory=lambda: {"max_retries": 3, "backoff": "exponential"})
    domain: str = "general"
    
    # Runtime stats
    total_calls: int = 0
    success_calls: int = 0

    @property
    def success_rate(self) -> float:
        if self.total_calls == 0:
            return 1.0
        return self.success_calls / self.total_calls


class SkillRegistry:
    """
    [V11.1] Dynamic Skill Registry for J.A.R.V.I.S.
    
    Bridges the tool system with the cognitive architecture by wrapping
    each tool as a "skill" with metadata for intelligent selection.
    
    Features:
    - Auto-registration from ToolRegistry
    - Capability matching by domain
    - Cost-aware skill selection
    - Runtime success tracking
    """
    def __init__(self):
        self.skills: Dict[str, Skill] = {}
        self._initialized = False

    def register_skill(self, skill: Skill):
        self.skills[skill.name] = skill
        logger.debug(f"Skill registered: {skill.name}")

    def register_from_tool_registry(self, tool_registry):
        """
        Auto-registers all tools from the legacy ToolRegistry as skills.
        Called during engine initialization.
        """
        if self._initialized:
            return
            
        try:
            for tag in tool_registry.all_tags:
                tool = tool_registry.get_by_protocol(tag)
                if tool:
                    skill = Skill(
                        name=tool.name,
                        description=tool.description,
                        input_schema=tool.parameters or {},
                        output_schema={"result": "ToolResult"},
                        protocol_tag=tag,
                        domain=getattr(tool, 'domain', 'general'),
                        execution_cost=max(1, getattr(tool, 'latency_ms', 500) // 500),
                        confidence=getattr(tool, 'reliability_score', 0.9),
                    )
                    self.register_skill(skill)
            
            self._initialized = True
            logger.info(f"SkillRegistry: {len(self.skills)} skills registered from ToolRegistry.")
        except Exception as e:
            logger.error(f"SkillRegistry auto-registration failed: {e}")

    def get_skill(self, name: str) -> Optional[Skill]:
        return self.skills.get(name)

    def get_by_protocol(self, tag: str) -> Optional[Skill]:
        """Find skill by protocol tag."""
        for skill in self.skills.values():
            if skill.protocol_tag == tag:
                return skill
        return None

    def list_skills(self) -> List[str]:
        return list(self.skills.keys())

    def get_skills_by_domain(self, domain: str) -> List[Skill]:
        """Returns all skills matching a domain."""
        return [s for s in self.skills.values() if s.domain == domain]

    def get_best_skill(self, domain: str) -> Optional[Skill]:
        """Returns the most reliable and cheapest skill for a domain."""
        candidates = self.get_skills_by_domain(domain)
        if not candidates:
            return None
        # Sort by: reliability desc, cost asc
        candidates.sort(key=lambda s: (-s.success_rate, s.execution_cost))
        return candidates[0]

    def record_execution(self, skill_name: str, success: bool):
        """Records skill execution result for runtime stats."""
        skill = self.skills.get(skill_name)
        if skill:
            skill.total_calls += 1
            if success:
                skill.success_calls += 1

    def get_skills_prompt(self) -> str:
        """Generates a prompt describing available skills for the LLM."""
        if not self.skills:
            return "No skills registered."
        
        prompt = "AVAILABLE SKILLS:\n"
        for name, skill in self.skills.items():
            tag_info = f" [{skill.protocol_tag}]" if skill.protocol_tag else ""
            prompt += (
                f"- {name}{tag_info}: {skill.description} "
                f"(Domain: {skill.domain}, Cost: {skill.execution_cost}, "
                f"Reliability: {skill.success_rate:.0%})\n"
            )
        return prompt

    def get_stats(self) -> Dict[str, Any]:
        """Returns skill registry statistics."""
        total = len(self.skills)
        domains = {}
        for s in self.skills.values():
            domains[s.domain] = domains.get(s.domain, 0) + 1
        
        return {
            "total_skills": total,
            "domains": domains,
            "initialized": self._initialized,
            "top_skills": sorted(
                [(s.name, s.success_rate) for s in self.skills.values() if s.total_calls > 0],
                key=lambda x: -x[1]
            )[:5]
        }
