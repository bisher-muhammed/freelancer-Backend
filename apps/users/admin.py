from django.contrib import admin
from.models import ClientProfile,User,UserSubscription,Project
from apps.freelancer.models import Education,EmploymentHistory ,FreelancerProfile,Skill,FreelancerSkill,Category

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


