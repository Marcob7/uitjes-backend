from django.contrib import admin
from .models import City, Venue, Event, Feedback

admin.site.register(City)
admin.site.register(Venue)
admin.site.register(Event)



@admin.register(Feedback)
class FeedbackAdmin(admin.ModelAdmin):
    # Dit zijn de kolommen die je ziet in het lijst-overzicht
    list_display = ("id", "created_at", "email", "short_message", "page_url")

    # Dit maakt het snel zoeken in admin
    search_fields = ("message", "email", "page_url")

    # Dit maakt filtering rechts mogelijk (handig bij veel feedback)
    list_filter = ("created_at",)

    # Dit zorgt dat je nieuwste feedback bovenaan ziet
    ordering = ("-created_at",)

    # Kleine helper om het bericht kort te tonen in de lijst
    @admin.display(description="message")
    def short_message(self, obj):
        return obj.message[:60] + ("…" if len(obj.message) > 60 else "")
