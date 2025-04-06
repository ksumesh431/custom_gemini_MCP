import asyncio
import os
import json
import aiohttp
from google import genai
from google.genai import types
import readline


from dotenv import load_dotenv

load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
MCP_API_URL = os.getenv("MCP_API_URL")

client = genai.Client(api_key=GEMINI_API_KEY)


async def call_tool(session, tool_name, parameters):
    payload = {"tool_name": tool_name, "parameters": parameters}
    async with session.post(f"{MCP_API_URL}/call_tool", json=payload) as resp:
        return await resp.json()


async def main():
    async with aiohttp.ClientSession() as session:
        # Fetch tool schemas
        async with session.get(f"{MCP_API_URL}/list_tools") as resp:
            data = await resp.json()
            tools = [
                types.Tool(
                    function_declarations=[
                        {
                            "name": tool["name"],
                            "description": tool["description"],
                            "parameters": tool["inputSchema"],
                        }
                    ]
                )
                for tool in data["tools"]
            ]

        # User input
        user_input = input("Enter CloudFront distribution ID: ").strip()

        # Optimized initial prompt for Flash models
        prompt = (
            f"You are an AWS CloudFront expert assistant.\n"
            f"Your task is to analyze the CloudFront distribution '{user_input}'.\n"
            "Follow these steps:\n"
            "1. Use the tools to fetch the distribution info.\n"
            "2. Use the tools to fetch recent CloudFront logs.\n"
            "3. Use the tools to analyze the logs.\n"
            "4. Provide clear, actionable remediations and recommendations based on the analysis in formatted points.\n"
            "Do not guess. Always use the tools before answering.\n"
        )

        # Conversation history
        history = [prompt]

        while True:
            response = client.models.generate_content(
                model="gemini-2.0-flash",  # use Flash model
                contents="\n".join(history),
                config=types.GenerateContentConfig(
                    temperature=0,
                    tools=tools,
                ),
            )

            candidate = response.candidates[0]

            if not candidate.content or not candidate.content.parts:
                print("\nNo response from Gemini.")
                break

            part = candidate.content.parts[0]

            if hasattr(part, "function_call") and part.function_call:
                function_call = part.function_call
                # Call MCP server tool
                tool_result = await call_tool(
                    session, function_call.name, function_call.args
                )
                # Add tool result to conversation history
                tool_result_str = json.dumps(tool_result, indent=2)
                history.append(
                    f"Tool call '{function_call.name}' result:\n{tool_result_str}"
                )
                continue  # Loop again, Gemini will use this info

            elif hasattr(part, "text") and part.text:
                print("\n--- Gemini Response ---\n")
                print(part.text)
                history.append(part.text)

            else:
                print("\nNo response text from Gemini.")
                break

            # User follow-up
            follow_up = input("\nAsk a follow-up question (or 'exit'): ").strip()
            if follow_up.lower() == "exit":
                break
            history.append(follow_up)


if __name__ == "__main__":
    asyncio.run(main())
