import os
from io import BytesIO
from pathlib import Path
from typing import List
import json
from typing_extensions import override

import openai # Added import
from openai import AsyncAssistantEventHandler, AsyncOpenAI, OpenAI
from openai.types.beta.threads.runs import ToolCall, ToolCallDelta,RunStepDelta,RunStep

from literalai.helper import utc_now
import chainlit as cl
from chainlit.config import config
from chainlit.element import Element


async_openai_client = AsyncOpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
sync_openai_client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

try:
    assistant = sync_openai_client.beta.assistants.retrieve(
        os.environ.get("OPENAI_ASSISTANT_ID")
    )
    config.ui.name = assistant.name
except openai.APIError as e:
    print(f"OpenAI API Error retrieving assistant: {e}. The application may not function correctly.")
    assistant = None # Ensure assistant is None so later checks can handle it
    config.ui.name = "Error: Assistant Not Loaded"
except Exception as e:
    print(f"Unexpected error retrieving assistant: {e}. The application may not function correctly.")
    assistant = None
    config.ui.name = "Error: Assistant Not Loaded"



#how to add customized functions
# 1. edit class attribute function_map, key is the function name you regiesterd in openai's system, you can add function through playground or api 
# value is the actual function you are going to implement
# 2. implement the function in the class,make sure the arguments name match with the parameters 

class EventHandler(AsyncAssistantEventHandler):

    def __init__(self, assistant_name: str) -> None:
        super().__init__()
        self.current_message: cl.Message = None
        self.current_step: cl.Step = None
        self.current_tool_call = None
        self.assistant_name = assistant_name
        self.function_map={'search_web':self.search_web,
                           'add_two_numbers':self.add_two_numbers}
    
    

    #implment search_web function.
    def search_web(self,query):
        print('search_web -----> query:',query)
        return 'currently unimplemented, please implement this function '+query
    
    #an example function that is already implemented
    def add_two_numbers(self,number1,number2):
        return str(number1+number2)

    @override
    async def on_event(self, event):
      # Retrieve events that are denoted with 'requires_action',since these will have our tool_calls
      if event.event == 'thread.run.requires_action':
        run_id = event.data.id  # Retrieve the run ID from the event data
        self.current_run.id=run_id
        await self.handle_requires_action(event.data, run_id)


    async def handle_requires_action(self, data, run_id):
        tool_outputs = []
        for tool in data.required_action.submit_tool_outputs.tool_calls:
            func_name = tool.function.name
            func_args = tool.function.arguments

            # Use the instance attribute function_map
            func_to_call = self.function_map.get(func_name)
            
            if func_to_call:
                try:
                    # Parse the func_args JSON string to a dictionary
                    func_args_dict = json.loads(func_args)
                    tool_call_output = func_to_call(**func_args_dict)
                    tool_outputs.append({"tool_call_id": tool.id, "output": tool_call_output})
                except json.JSONDecodeError as e:
                    print(f"Error processing tool call: {tool.id}, function: {func_name}. Error: {e}")
                    tool_outputs.append({"tool_call_id": tool.id, "output": f"Error: Could not parse arguments for {func_name}. Details: {e}"})
                except TypeError as e:
                    print(f"Error processing tool call: {tool.id}, function: {func_name}. Error: {e}")
                    tool_outputs.append({"tool_call_id": tool.id, "output": f"Error: Invalid arguments for {func_name}. Details: {e}"})
                except Exception as e:
                    print(f"Error processing tool call: {tool.id}, function: {func_name}. Error: {e}")
                    tool_outputs.append({"tool_call_id": tool.id, "output": f"Error: Could not process tool call {func_name}. Details: {e}"})
            else:
                print(f"Function {func_name} not found")
                tool_outputs.append({"tool_call_id": tool.id, "output": f"Error: Function {func_name} not found."})
        # Submit all tool_outputs at the same time
        await self.submit_tool_outputs(tool_outputs, run_id)


    async def submit_tool_outputs(self, tool_outputs, run_id):
        """
        Submits the tool outputs to the current run.
        """
        try:
            async with async_openai_client.beta.threads.runs.submit_tool_outputs_stream(
                thread_id=self.current_run.thread_id,
                run_id=run_id,
                tool_outputs=tool_outputs,
                event_handler=EventHandler(assistant_name=self.assistant_name),
            ) as stream:
                await stream.until_done()
        except openai.APIError as e:
            print(f"OpenAI API Error submitting tool outputs: {e}")
            # Hard to send a message back to the user directly here, logging is key.

    

    async def on_text_created(self, text) -> None:
        try:
            self.current_message = await cl.Message(author=self.assistant_name, content="").send()
        except Exception as e:
            print(f"Error in on_text_created: {e}")
            # Attempt to send an error message if message creation failed
            await cl.ErrorMessage(content=f"Error creating message: {e}").send()

    async def on_text_delta(self, delta, snapshot):
        try:
            if self.current_message and hasattr(delta, 'value'):
                await self.current_message.stream_token(delta.value)
            elif not self.current_message:
                print("Error in on_text_delta: self.current_message is None. Cannot stream token.")
        except Exception as e:
            print(f"Error in on_text_delta: {e}")
            # Streaming token to a message that might be compromised is risky. Logging is primary.

    async def on_text_done(self, text):
        try:
            if self.current_message:
                await self.current_message.update()
            else:
                print("Error in on_text_done: self.current_message is None. Cannot update.")
        except Exception as e:
            print(f"Error in on_text_done: {e}")
            # If current_message exists, try to set its content to an error message.
            if self.current_message:
                self.current_message.content = f"Error finalizing message: {e}"
                try:
                    await self.current_message.update()
                except Exception as update_e:
                    print(f"Error updating message with error state: {update_e}")
            else:
                await cl.ErrorMessage(content=f"Error finalizing message: {e}").send()

    async def on_tool_call_delta(self, delta, snapshot):
        try:
            if hasattr(snapshot, 'id') and snapshot.id != self.current_tool_call :
                self.current_tool_call = snapshot.id
                # Ensure delta.type exists before creating Step
                step_name = delta.type if hasattr(delta, 'type') else "tool_call"
                self.current_step = cl.Step(name=step_name, type="tool")
                self.current_step.language = "python" # Default, can be overridden
                self.current_step.start = utc_now()
                # Not sending the step immediately: await self.current_step.send()

            if hasattr(delta, 'type') and delta.type == "code_interpreter":
                if hasattr(delta, 'code_interpreter') and delta.code_interpreter:
                    if delta.code_interpreter.outputs:
                        for output in delta.code_interpreter.outputs:
                            if hasattr(output, 'type') and output.type == "logs":
                                # Ensure self.current_step exists from the initial part of the method
                                if not self.current_step:
                                    print("Error in on_tool_call_delta: self.current_step is None when processing logs.")
                                    # Create a generic step if needed, though context might be lost
                                    self.current_step = cl.Step(name="code_interpreter_log_error", type="tool")
                                    self.current_step.start = utc_now()


                                error_step_name = delta.type # or a more specific name
                                error_step = cl.Step(name=error_step_name,type="tool")
                                error_step.is_error = True
                                error_step.output = output.logs if hasattr(output, 'logs') else "Unknown error log"
                                error_step.language = "markdown"
                                error_step.start = self.current_step.start if self.current_step and self.current_step.start else utc_now()
                                error_step.end = utc_now()
                                await error_step.send()
                    elif delta.code_interpreter.input:
                        if self.current_step:
                            await self.current_step.stream_token(delta.code_interpreter.input)
                        else:
                            print("Error in on_tool_call_delta: self.current_step is None. Cannot stream input token.")
            # Potentially add handling for other delta.type if necessary
        except Exception as e:
            print(f"Error in on_tool_call_delta: {e}")
            # It's hard to show this error in the UI if the step itself is compromised. Logging is crucial.
            # If a step was being built, try to mark it as error or send a general error.
            if self.current_step and self.current_step.output is None : # Avoid overwriting existing output
                 self.current_step.output = f"Error processing tool call delta: {e}"
                 self.current_step.is_error = True
                 try:
                     await self.current_step.update() # or send if not yet sent
                 except Exception as step_update_e:
                     print(f"Error updating step with error state in on_tool_call_delta: {step_update_e}")


    async def on_run_step_done(self, run_step: RunStep):
        try:
            if not hasattr(run_step, 'type') or not hasattr(run_step, 'step_details'):
                print(f"Error in on_run_step_done: run_step is missing 'type' or 'step_details'. run_step: {run_step}")
                return

            if run_step.type == 'tool_calls':
                tool_calls = run_step.step_details.tool_calls if hasattr(run_step.step_details, 'tool_calls') else []

                if any(hasattr(call, 'type') and call.type == 'file_search' for call in tool_calls):
                    # The sync_openai_client call here could also be wrapped, but it's outside the scope of this subtask's direct client calls.
                    # For now, focusing on the event handler's robustness.
                    try:
                        retrieved_run_step = sync_openai_client.beta.threads.runs.steps.retrieve(
                            thread_id=cl.user_session.get("thread_id"), # Potential for session errors
                            run_id=run_step.run_id,
                            step_id=run_step.id,
                            include=["step_details.tool_calls[*].file_search.results[*].content"]
                        )
                        # Re-assign tool_calls from the retrieved step for fresh details
                        tool_calls = retrieved_run_step.step_details.tool_calls if hasattr(retrieved_run_step.step_details, 'tool_calls') else []
                    except openai.APIError as api_e:
                        print(f"OpenAI API Error retrieving run step details in on_run_step_done: {api_e}")
                        # Create an error step to inform user if possible
                        error_step = cl.Step(name="file_search_error", type="tool")
                        error_step.output = f"Failed to retrieve file search results: {api_e}"
                        error_step.is_error = True
                        await error_step.send()
                        return # Stop further processing for this event
                    except Exception as e:
                        print(f"Error retrieving run step details in on_run_step_done: {e}")
                        # Create an error step
                        error_step = cl.Step(name="file_search_detail_error", type="tool")
                        error_step.output = f"Unexpected error retrieving file search details: {e}"
                        error_step.is_error = True
                        await error_step.send()
                        return


                    citations = []
                    last_call_type_for_step_name = "file_search" # Default
                    for call in tool_calls:
                        if hasattr(call, 'type') and call.type == 'file_search':
                            last_call_type_for_step_name = call.type
                            if hasattr(call, 'file_search') and call.file_search and hasattr(call.file_search, 'results'):
                                for result in call.file_search.results:
                                    quote = result.content[0].text if hasattr(result, 'content') and result.content and hasattr(result.content[0], 'text') else ""
                                    citations.append({
                                        "file_name": getattr(result, 'file_name', 'Unknown file'),
                                        "score": getattr(result, 'score', 0),
                                        "quote": quote
                                    })

                    citations_dict = {"citations": citations}
                    self.current_step = cl.Step(name=last_call_type_for_step_name, type="tool")
                    self.current_step.output = citations_dict
                    await self.current_step.send()

                else: # Handle other tool calls (e.g. custom functions)
                    for tool_call in tool_calls:
                        if hasattr(tool_call, 'function'):
                            func_name = getattr(tool_call.function, 'name', 'unknown_function')
                            func_args = getattr(tool_call.function, 'arguments', '{}')
                            func_output = getattr(tool_call.function, 'output', None)

                            current_tool_step = cl.Step(name=func_name, type="tool")
                            try:
                                current_tool_step.input = json.loads(func_args)
                            except json.JSONDecodeError:
                                current_tool_step.input = {"error": "Invalid JSON arguments", "args": func_args}

                            if func_output is not None:
                                try:
                                    current_tool_step.output = json.loads(func_output)
                                except json.JSONDecodeError:
                                    current_tool_step.output = func_output # Treat as plain text
                            else:
                                current_tool_step.output = "No output from function." # Or handle as error

                            await current_tool_step.send()
            # Potentially handle other run_step.type like 'message_creation' if needed, though usually handled by on_text_xxx
        except Exception as e:
            print(f"Error in on_run_step_done: {e}")
            # It's hard to show this error in the UI if the step itself is compromised. Logging is crucial.
            # If a step was being built, try to mark it as error or send a general error.
            if self.current_step and self.current_step.output is None:
                 self.current_step.output = f"Error processing run step: {e}"
                 self.current_step.is_error = True
                 try:
                     await self.current_step.update() # or send if not yet sent
                 except Exception as step_update_e:
                     print(f"Error updating step with error state in on_run_step_done: {step_update_e}")


    async def on_image_file_done(self, image_file):
        image_id = image_file.file_id
        try:
            response = await async_openai_client.files.with_raw_response.content(image_id)
            image_element = cl.Image(
                name=image_id,
                content=response.content,
                display="inline",
                size="large"
            )
            if not self.current_message.elements:
                self.current_message.elements = []
            self.current_message.elements.append(image_element)
            await self.current_message.update()
        except openai.APIError as e:
            print(f"OpenAI API Error fetching image content for {image_id}: {e}")
            if self.current_message:
                self.current_message.content = f"Error displaying image {image_id}. Details: {e}"
                await self.current_message.update()
            else:
                # This case might be less common if on_image_file_done is usually tied to a message
                await cl.ErrorMessage(content=f"Failed to load image {image_id}. Details: {e}").send()
        except Exception as e:
            print(f"Unexpected error in on_image_file_done for {image_id}: {e}")
            if self.current_message:
                self.current_message.content = f"Unexpected error displaying image {image_id}."
                await self.current_message.update()
            else:
                await cl.ErrorMessage(content=f"Unexpected error loading image {image_id}.").send()


@cl.step(type="tool")
async def speech_to_text(audio_file):
    try:
        response = await async_openai_client.audio.transcriptions.create(
            model="whisper-1", file=audio_file
        )
        return response.text
    except openai.APIError as e:
        print(f"OpenAI API Error during speech to text: {e}")
        raise # Re-raise to be handled by the caller
    except Exception as e:
        print(f"Unexpected error during speech to text: {e}")
        raise # Re-raise to be handled by the caller

async def upload_files(files: List[Element]):
    file_ids = []
    errors = []
    for file_idx, file in enumerate(files):
        try:
            uploaded_file = await async_openai_client.files.create(
                file=Path(file.path), purpose="assistants"
            )
            file_ids.append(uploaded_file.id)
        except openai.APIError as e:
            print(f"OpenAI API Error uploading file {file.name or f'file_{file_idx}'}: {e}")
            errors.append({"file_name": file.name or f'file_{file_idx}', "error": str(e)})
        except Exception as e:
            print(f"Error processing file {file.name or f'file_{file_idx}'} for upload: {e}")
            errors.append({"file_name": file.name or f'file_{file_idx}', "error": str(e)})

    if errors:
        error_messages = [f"{err['file_name']}: {err['error']}" for err in errors]
        # It's better to raise a custom exception or handle this more gracefully
        # For now, raising a general exception with a summary
        raise Exception(f"Failed to upload some files: {'; '.join(error_messages)}")
    return file_ids


async def process_files(files: List[Element]):
    # Upload files if any and get file_ids
    file_ids = []
    if len(files) > 0:
        file_ids = await upload_files(files)

    return [
        {
            "file_id": file_id,
            "tools": [{"type": "code_interpreter"}, {"type": "file_search"}],
        }
        for file_id in file_ids
    ]


@cl.on_chat_start
async def start_chat():
    try:
        # Create a Thread
        thread = await async_openai_client.beta.threads.create()
        # Store thread ID in user session for later use
        cl.user_session.set("thread_id", thread.id)
    except openai.APIError as e:
        print(f"OpenAI API Error on chat start (thread creation): {e}")
        await cl.ErrorMessage(content=f"Failed to start chat. OpenAI API Error: {e}. Please try again later.").send()
    except Exception as e:
        print(f"Unexpected error on chat start: {e}")
        await cl.ErrorMessage(content=f"An unexpected error occurred while starting the chat: {e}.").send()

@cl.on_message
async def main(message: cl.Message):
    if not assistant:
        await cl.ErrorMessage(content="The Assistant is not available due to an earlier initialization error. Please check server logs.").send()
        return

    thread_id = cl.user_session.get("thread_id")
    if not thread_id:
        # This case can happen if start_chat failed to set the thread_id
        await cl.ErrorMessage(content="Chat session not properly initialized. Please refresh and try again.").send()
        return

    try:
        attachments = await process_files(message.elements)

        # Add a Message to the Thread
        oai_message = await async_openai_client.beta.threads.messages.create(
            thread_id=thread_id,
            role="user",
            content=message.content,
            attachments=attachments,
        )

        # Create and Stream a Run
        # Ensure assistant.id and assistant.name are accessed only if assistant is not None
        if assistant and assistant.id and assistant.name:
            async with async_openai_client.beta.threads.runs.stream(
                thread_id=thread_id,
                assistant_id=assistant.id,
                event_handler=EventHandler(assistant_name=assistant.name),
            ) as stream:
                await stream.until_done()
        else:
            # This should ideally not be reached if the top check for assistant works,
            # but as a safeguard:
            await cl.ErrorMessage(content="Assistant configuration is missing. Cannot process message.").send()
            return

    except openai.APIError as e:
        print(f"OpenAI API Error in main message processing: {e}")
        await cl.ErrorMessage(content=f"An error occurred with the OpenAI API while processing your message: {e}.").send()
    except Exception as e: # Catch other errors, like from process_files if it raises one
        print(f"Error in main message processing: {e}")
        await cl.ErrorMessage(content=f"An unexpected error occurred: {e}.").send()


@cl.on_audio_chunk
async def on_audio_chunk(chunk: cl.AudioChunk):
    if chunk.isStart:
        buffer = BytesIO()
        # This is required for whisper to recognize the file type
        buffer.name = f"input_audio.{chunk.mimeType.split('/')[1]}"
        # Initialize the session for a new audio stream
        cl.user_session.set("audio_buffer", buffer)
        cl.user_session.set("audio_mime_type", chunk.mimeType)

    # Write the chunks to a buffer and transcribe the whole audio at the end
    cl.user_session.get("audio_buffer").write(chunk.data)


@cl.on_audio_end
async def on_audio_end(elements: list[Element]):
    # Get the audio buffer from the session
    audio_buffer: BytesIO = cl.user_session.get("audio_buffer")
    audio_buffer.seek(0)  # Move the file pointer to the beginning
    audio_file = audio_buffer.read()
    audio_mime_type: str = cl.user_session.get("audio_mime_type")

    input_audio_el = cl.Audio(
        mime=audio_mime_type, content=audio_file, name=audio_buffer.name
    )
    await cl.Message(
        author="You",
        type="user_message",
        content="",
        elements=[input_audio_el, *elements],
    ).send()

    whisper_input = (audio_buffer.name, audio_file, audio_mime_type)
    try:
        transcription = await speech_to_text(whisper_input)
        msg = cl.Message(author="You", content=transcription, elements=elements)
        await main(message=msg)
    except openai.APIError as e:
        # Error is already logged by speech_to_text
        await cl.ErrorMessage(content=f"Failed to transcribe audio due to OpenAI API error: {e}. Please try again.").send()
    except Exception as e:
        # For other exceptions re-raised by speech_to_text or new ones here
        print(f"Error in on_audio_end: {e}")
        await cl.ErrorMessage(content=f"An unexpected error occurred during audio processing: {e}.").send()


if __name__ == "__main__":
    from chainlit.cli import run_chainlit
    # Check if assistant was loaded before running Chainlit, though Chainlit's run controls the main loop.
    # This is more of a warning for the developer.
    if not assistant:
        print("Warning: OpenAI Assistant could not be initialized. Chainlit app might not work as expected.")
    run_chainlit(__file__)