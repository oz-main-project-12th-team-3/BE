from schedule.services.schedule_service import (
    create_schedule,
    delete_schedule,
    get_schedules_for_user,
    update_schedule,
)


class AIService:
    def __init__(self, client):
        self.client = client

    def generate_prompt(self, user_message, schedules):
        system_prompt = (
            "너는 친절한 일정 관리 비서야.\n"
            "아래는 사용자의 현재 일정 목록이야.\n"
            + "\n".join(
                [
                    (
                        f"{s.title} (시작: {s.start_time}, "
                        f"종료: {s.end_time}, 완료: {s.is_completed})"
                    )
                    for s in schedules
                ]
            )
            + "\n\n"
        )

        prompt = (
            system_prompt
            + "아래 사용자의 메시지를 보고 일정 생성, 수정, 삭제 여부와 "
            + "그 내용을 판단해.\n"
            + "명확하게 생성(create), 수정(update), 삭제(delete) 작업인지 "
            + "분리해서 JSON 형태로 다음 구조에 맞게 답변해줘:\n"
            + '{ "action": "create|update|delete|none", '
            + '"schedule": { "id": int|null, "title": str|null, '
            + '"description": str|null, "start_time": str|null, '
            + '"end_time": str|null, "is_completed": bool|null } }\n'
            + "만약 일정 변경이 아니라면 action을 'none'으로 해줘.\n"
            + "사용자 메시지:\n"
            + user_message
            + "\nJSON으로만 답변해줘."
        )

        return prompt

    def ask_schedule_assistant(self, user, user_message):
        schedules = get_schedules_for_user(user)
        prompt = self.generate_prompt(user_message, schedules)
        response = self.client.chat.completions.create(
            model="gemini-2.5-flash",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=400,
            temperature=0.5,
        )
        return response.choices[0].message.content

    def parse_response(self, response_text):
        try:
            import json

            return json.loads(response_text)
        except Exception:
            return {"action": "none"}

    def process_schedule_command(self, user, user_message):
        raw_response = self.ask_schedule_assistant(user, user_message)
        parsed = self.parse_response(raw_response)

        action = parsed.get("action", "none")
        schedule_data = parsed.get("schedule", {})

        if action == "create":
            # 최소한 제목은 필요
            title = schedule_data.get("title")
            if not title:
                return "일정을 생성하려면 제목이 필요합니다."
            create_schedule(user, schedule_data)
            return f"일정 '{title}'를 생성했습니다."

        elif action == "update":
            schedule_id = schedule_data.get("id")
            if not schedule_id:
                return "수정할 일정의 ID가 필요합니다."
            try:
                update_schedule(user, schedule_id, schedule_data)
                return f"일정 ID {schedule_id}를 수정했습니다."
            except Exception as e:
                return f"일정 수정 실패: {str(e)}"

        elif action == "delete":
            schedule_id = schedule_data.get("id")
            if not schedule_id:
                return "삭제할 일정의 ID가 필요합니다."
            try:
                delete_schedule(user, schedule_id)
                return f"일정 ID {schedule_id}를 삭제했습니다."
            except Exception as e:
                return f"일정 삭제 실패: {str(e)}"

        else:
            # 변경 작업이 아닌 경우 일반 문의로 판단
            return None
