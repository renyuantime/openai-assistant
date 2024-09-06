# OpenAI Assistant

You can deploy your OpenAI assistant with Chainlit using this template.
![openai-assistant](https://github.com/Chainlit/openai-assistant/assets/13104895/5c095a89-e426-417e-977d-772c4d4974c2)

### Supported Assistant Features


| Streaming | Files | Code Interpreter | File Search | Voice | Function Call |
| --------- | ----- | ---------------- | ----------- | ----- | -------------- |
| ✅        | ✅    | ✅               | ✅          | ✅    | ✅             |


#### How to Use the Function Call Feature


![openai-assistant-funciton-call](https://github.com/user-attachments/assets/920767aa-29af-493c-a88b-9dd0137c3108)

---

#### How to Implement Customized Functions

To implement custom functions with OpenAI's function call feature, follow these steps:

1. **Register Your Function**
   - Register your function through the OpenAI API or in the Playground. Ensure that the function names and their parameters are properly defined.

    ```json
      {
        "name": "search_web",
        "description": "search information online",
        "strict": true,
        "parameters": {
          "type": "object",
          "properties": {
            "query": {
              "type": "string",
              "description": "search query for web search"
            }
          },
          "additionalProperties": false,
          "required": [
            "query"
          ]
        }
      }
     ```

     ```json
      {
        "name": "add_two_numbers",
        "description": "add two numbers together",
        "strict": true,
        "parameters": {
          "type": "object",
          "properties": {
            "number1": {
              "type": "integer",
              "description": "the first number for the addinng operation"
            },
            "number2": {
              "type": "integer",
              "description": "the second number for the addinng operation"
            }
          },
          "additionalProperties": false,
          "required": [
            "number1",
            "number2"
          ]
        }
      }
     ```


     
2. **Edit the `function_map` Attribute in the `EventHandler` Class**
   - In the `EventHandler` class, edit the `function_map` attribute like so:
     ```python
     self.function_map = {
         'search_web': self.search_web,
         'add_two_numbers': self.add_two_numbers
     }
     ```
   - The **key names** (`'search_web'`, `'add_two_numbers'`) are the **function names** you registered with OpenAI, and they must match **exactly**.
   - The values (e.g., `self.search_web`, `self.add_two_numbers`) are the actual methods you will implement inside the `EventHandler` class.

3. **Implement the Functions**
   - Implement the functions that you registered and mapped in the `EventHandler` class. After the 'self' parameter, the parameter names and their count should exactly match the registered function in OpenAI’s system. For example:
     ```python
     def search_web(self, query):
         # Implementation of the search_web function
         pass

     def add_two_numbers(self, num1, num2):
         # Implementation of the add_two_numbers function
         return num1 + num2
     ```

---

### Get an OpenAI API key

Go to OpenAI's [API keys page](https://platform.openai.com/api-keys) and create one if you don't have one already.

### Create an Assistant

Go to OpenAI's [assistant page](https://platform.openai.com/assistants) and click on the `Create` at the top right.

Configure your assistant.

### [Optional] Get a Literal AI API key

> [!NOTE]  
> Literal AI is an all in one observability, evaluation and analytics platform for building LLM apps.

Go to [Literal AI](https://cloud.getliteral.ai/), create a project and go to Settings to get your API key.

### Deploy

Click on the button below, then set the API keys in the form and click on `Apply`.

[![Deploy to Render](https://render.com/images/deploy-to-render-button.svg)](https://render.com/deploy)
