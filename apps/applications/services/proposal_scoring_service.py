from datetime import date
from django.db import transaction
from django.utils import timezone

from apps.users.models import Project, User
from apps.applications.models import Proposal, ProposalScore, ProjectScoringConfig
from apps.freelancer.models import FreelancerProfile, FreelancerSkill, EmploymentHistory


class ProposalScoringService:
    """
    Computes and persists proposal scores.
    Deterministic, synchronous, no Celery, no LLM.
    """

    @classmethod
    def score_proposal(cls, proposal: Proposal) -> ProposalScore:
        project = proposal.project
        freelancer_user = proposal.freelancer

        config = cls._get_scoring_config(project)

        skill_match, missing_skills = cls._calculate_skill_match(project, freelancer_user)
        experience_match = cls._calculate_experience_match(project, freelancer_user)
        budget_fit = cls._calculate_budget_fit(project, proposal)
        reliability = cls._calculate_reliability(freelancer_user)

        final_score = (
            skill_match * config.skill_weight +
            experience_match * config.experience_weight +
            budget_fit * config.budget_weight +
            reliability * config.reliability_weight
        )

        # 🔎 Red flags are INFORMATION ONLY
        red_flags = []
        if skill_match < 30:
            red_flags.append("Low skill match")
        if experience_match < 30:
            red_flags.append("Low experience match")
        if reliability < 40:
            red_flags.append("Low reliability")

        # ✅ ONLY AUTO-REJECT RULE
        auto_reject = final_score < config.min_final_score
        auto_reject_reason = ""

        if auto_reject:
            auto_reject_reason = (
                f"Final score {final_score:.2f} "
                f"is below minimum required score {config.min_final_score}"
            )

        with transaction.atomic():
            score = ProposalScore.objects.create(
                proposal=proposal,
                experience_level=config.experience_level,
                skill_match=round(skill_match, 2),
                experience_match=round(experience_match, 2),
                budget_fit=round(budget_fit, 2),
                reliability=round(reliability, 2),
                final_score=round(final_score, 2),
                red_flags=red_flags,
                auto_reject=auto_reject,
                auto_reject_reason=auto_reject_reason,
                is_latest=True,
            )

            if auto_reject:
                proposal.status = "auto_rejected"
                proposal.rejected_at = timezone.now()
                proposal.rejection_reason = auto_reject_reason
                proposal.is_system_managed = True
                proposal.save(update_fields=[
                    "status",
                    "rejected_at",
                    "rejection_reason",
                    "is_system_managed",
                ])

        return score

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _get_scoring_config(project: Project) -> ProjectScoringConfig:
        try:
            return ProjectScoringConfig.objects.get(
                experience_level=project.experience_level
            )
        except ProjectScoringConfig.DoesNotExist:
            raise RuntimeError(
                f"No scoring config for experience level: {project.experience_level}"
            )

    # ------------------------------------------------------------------

    @staticmethod
    def _calculate_skill_match(project: Project, user: User):
        """
        Project.skills_required vs FreelancerSkill
        """
        try:
            profile = user.freelancerprofile
        except FreelancerProfile.DoesNotExist:
            required = list(project.skills_required.values_list("name", flat=True))
            return 0.0, required

        required_skills = set(
            project.skills_required.values_list("id", flat=True)
        )

        freelancer_skills = set(
            FreelancerSkill.objects.filter(
                freelancer=profile
            ).values_list("skill_id", flat=True)
        )

        if not required_skills:
            return 100.0, []

        matched = required_skills & freelancer_skills
        score = (len(matched) / len(required_skills)) * 100

        missing = list(
            project.skills_required.exclude(id__in=matched)
            .values_list("name", flat=True)
        )

        return score, missing

    # ------------------------------------------------------------------

    @staticmethod
    def _calculate_experience_match(project: Project, user: User):
        """
        Experience derived from EmploymentHistory.
        If end_date is NULL → today.
        """
        try:
            profile = user.freelancerprofile
        except FreelancerProfile.DoesNotExist:
            return 0.0

        jobs = EmploymentHistory.objects.filter(freelancer=profile)

        if not jobs.exists():
            return 0.0

        total_days = 0
        today = date.today()

        for job in jobs:
            if not job.start_date:
                continue
            end = job.end_date or today
            total_days += (end - job.start_date).days

        years = total_days / 365

        if project.experience_level == "entry":
            return min(100, (years / 2) * 100)

        if project.experience_level == "intermediate":
            return min(100, (years / 5) * 100)

        if project.experience_level == "expert":
            return min(100, (years / 10) * 100)

        return 0.0

    # ------------------------------------------------------------------

    @staticmethod
    def _calculate_budget_fit(project: Project, proposal: Proposal):
        """
        Uses correct model fields:
        - fixed_budget
        - hourly_min_rate / hourly_max_rate
        """
        if project.budget_type == "fixed":
            bid = proposal.bid_fixed_price
            budget = project.fixed_budget

            if bid <= budget:
                return 100 if bid < budget else 70

            diff_percent = ((bid - budget) / budget) * 100
            return max(0, 70 - diff_percent)

        if project.budget_type == "hourly":
            bid = proposal.bid_hourly_rate
            max_rate = project.hourly_max_rate

            if bid <= max_rate:
                return 100 if bid < max_rate else 70

            diff_percent = ((bid - max_rate) / max_rate) * 100
            return max(0, 70 - diff_percent)

        return 50.0

    # ------------------------------------------------------------------

    @staticmethod
    def _calculate_reliability(user: User):
        """
        Conservative default until you add real metrics.
        """
        try:
            profile = user.freelancerprofile
        except FreelancerProfile.DoesNotExist:
            return 0.0

        score = 100

        if not profile.is_verified:
            score -= 30

        # You can extend later:
        # - missed deadlines
        # - disputes
        # - completed jobs count

        return max(0, score)
