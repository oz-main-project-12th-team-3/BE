from users.models import User

from ..models import schedule


def get_schedules_for_user(user: User):
    """Returns queryset of schedules for a given user."""
    return Schedule.objects.filter(user=user)


def create_schedule(user: User, data: dict) -> Schedule:
    """Creates a new schedule for a given user."""
    data["user"] = user
    return Schedule.objects.create(**data)


def update_schedule(user: User, schedule_id: int, data: dict) -> Schedule:
    """Updates a schedule for a given user."""
    schedule = Schedule.objects.get(id=schedule_id, user=user)
    for key, value in data.items():
        setattr(schedule, key, value)
    schedule.save()
    return schedule


def delete_schedule(user: User, schedule_id: int):
    """Deletes a schedule for a given user."""
    schedule = Schedule.objects.get(id=schedule_id, user=user)
    schedule.delete()
