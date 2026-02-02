from django.contrib import admin

from apps.contract.models import Contract
from apps.tracking.models import Device, TimeBlock, WorkSession,Screenshot,ScreenshotWindow
from.models import ClientProfile,User,UserSubscription,Project
from apps.applications.models import Proposal,ProposalScore,Meeting,Offer
from apps.freelancer.models import Education,EmploymentHistory ,FreelancerProfile,Skill,FreelancerSkill,Category
from apps.tracking.models import WorkConsent
from apps.billing.models import *


admin.site.register(ClientProfile)
admin.site.register(User)
admin.site.register(Education)
admin.site.register(FreelancerProfile)
admin.site.register(EmploymentHistory)
admin.site.register(Skill)
admin.site.register(FreelancerSkill)
admin.site.register(Category)
admin.site.register(UserSubscription)
admin.site.register(Project)
admin.site.register(Proposal)
admin.site.register(ProposalScore)
admin.site.register(Meeting)
admin.site.register(Offer)
admin.site.register(Contract)
admin.site.register(Device)
admin.site.register(WorkConsent)
admin.site.register(TimeBlock)
admin.site.register(WorkSession)
admin.site.register(ScreenshotWindow)
admin.site.register(Screenshot)
admin.site.register(BillingUnit)
admin.site.register(PayoutBatch)