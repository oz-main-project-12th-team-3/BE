from rest_framework import serializers

from .models import PaymentHistory, Plan, Subscription


class PlanSerializer(serializers.ModelSerializer):
    class Meta:
        model = Plan
        fields = [
            "id",
            "name",
            "description",
            "price",
            "billing_cycle",
            "included_units",
            "is_active",
        ]
        read_only_fields = fields


class SubscriptionSerializer(serializers.ModelSerializer):
    plan_name = serializers.CharField(
        source="plan.name",
        read_only=True,
    )

    class Meta:
        model = Subscription
        fields = [
            "id",
            "user",
            "plan",
            "plan_name",
            "price",
            "status",
            "remaining_units",
            "start_date",
            "end_date",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "user",
            "plan",
            "price",
            "status",
            "start_date",
            "end_date",
            "created_at",
            "updated_at",
        ]


class PaymentHistorySerializer(serializers.ModelSerializer):
    plan_name = serializers.CharField(
        source="plan.name",
        read_only=True,
        allow_null=True,
    )

    class Meta:
        model = PaymentHistory
        fields = [
            "id",
            "user",
            "plan",
            "plan_name",
            "subscription",
            "order_id",
            "amount",
            "status",
            "payment_method",
            "transaction_id",
            "paid_at",
            "created_at",
        ]
        read_only_fields = fields
