from django.db import models


class SubscriptionPlan(models.Model):
    name = models.CharField(max_length=100,unique=True)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    max_projects = models.IntegerField(default=1)
    duration_days = models.IntegerField(default=30)  

    def __str__(self):
        return f"{self.name} - ${self.price}"   
    

class TrackingPolicy(models.Model):
    version = models.CharField(max_length=20, unique=True)  
    title = models.CharField(max_length=255)
    content = models.TextField()  
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
