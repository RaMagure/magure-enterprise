from LLM import LLM
import os


def test_llm_initialization():
    llm = LLM(
        api_key="",
        selected_model="gpt-2.5",
    )
    while True:
        user_input = input("User: ")
        print(llm.chat(user_input))


test_llm_initialization()
