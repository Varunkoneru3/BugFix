import streamlit as st
import google.generativeai as genai
import os
import re # Import regular expressions for parsing

# --- Configuration ---
# (Keep the API key configuration as before)
try:
    GOOGLE_API_KEY =st.secrets["GOOGLE_API_KEY"]
   
except (FileNotFoundError, KeyError):
    GOOGLE_API_KEY = os.environ.get("GOOGLE_API_KEY")
    if not GOOGLE_API_KEY:
        st.warning("⚠️ Google API Key not found. Please set it in Streamlit Secrets or as an environment variable (GOOGLE_API_KEY). Features will be limited.")

genai_configured = False
if GOOGLE_API_KEY:
    try:
        genai.configure(api_key=GOOGLE_API_KEY)
        model = genai.GenerativeModel('gemini-1.5-flash') # Or 'gemini-pro'
        genai_configured = True
    except Exception as e:
        st.error(f"❌ Error configuring Google AI: {e}")
else:
     pass # Warning already shown if key missing


# --- Improved Helper Function to Parse AI Response ---
def parse_ai_response(response_text):
    """
    Parses the AI response text more robustly.
    Looks for headings and extracts content between them or until the end.
    Specifically isolates the code block under 'Corrected Code'.
    Returns a dictionary with extracted sections and a boolean indicating overall parsing success.
    """
    sections = {
        "error_details": None,
        "corrected_code": None,
        "suggestions": None
    }
    parsing_successful = True # Assume success initially

    # --- Extract Error Details ---
    # Look for Error Details heading, capture until the next heading or end of string
    error_match = re.search(
        r"## Error Details\s*(.*?)\s*(?=## Corrected Code|## Suggestions|\Z)",
        response_text,
        re.DOTALL | re.IGNORECASE
    )
    if error_match:
        sections["error_details"] = error_match.group(1).strip()
    else:
        # Don't mark as total failure yet, maybe only suggestions are missing
        if "error details" in response_text.lower():
             sections["error_details"] = "[Parsing Error: Could not isolate Error Details section]"
        parsing_successful = False # Essential part missing

    # --- Extract Corrected Code ---
    # Look for Corrected Code heading, then find the *first* code block immediately after it
    corrected_code_heading_match = re.search(
        r"## Corrected Code\s*",
        response_text,
        re.IGNORECASE
    )
    if corrected_code_heading_match:
        # Start searching for the code block *after* the heading
        search_start_index = corrected_code_heading_match.end()
        code_block_match = re.search(
            r"```(?:[a-zA-Z]*\n)?(.*?)\n```",
            response_text[search_start_index:], # Search only in the remainder
            re.DOTALL
        )
        if code_block_match:
            sections["corrected_code"] = code_block_match.group(1).strip()
        else:
            # Heading found, but no code block right after?
             if "corrected code" in response_text.lower(): # Check if the phrase exists at all
                 sections["corrected_code"] = "[Parsing Error: Found 'Corrected Code' heading but no valid code block immediately after it]"
             parsing_successful = False # Essential part missing or malformed
    else:
         if "corrected code" in response_text.lower():
             sections["corrected_code"] = "[Parsing Error: Could not find '## Corrected Code' heading]"
         parsing_successful = False # Essential part missing

    # --- Extract Suggestions ---
    # Look for Suggestions heading, capture everything *after* it until the end
    suggestions_match = re.search(
        r"## Suggestions\s*(.*)",
        response_text,
        re.DOTALL | re.IGNORECASE
    )
    if suggestions_match:
        # Further check: Does the suggestion text *start* with a code block that might belong above?
        # This is tricky, let's keep it simple for now and just extract everything.
        # If the AI puts code here, it will show up here.
        sections["suggestions"] = suggestions_match.group(1).strip()
        # If suggestions are empty, that's okay, don't mark parsing as failed
        if not sections["suggestions"]:
             sections["suggestions"] = "[No specific suggestions provided.]"

    else:
        # Suggestions might be optional, so don't mark parsing as failed *just* for this
        if "suggestions" in response_text.lower():
             sections["suggestions"] = "[Parsing Error: Could not isolate Suggestions section]"
        # If suggestions are truly missing, set to None or an indicator message
        # sections["suggestions"] = None # Or keep as None if preferred

    # Final check: If essential parts are missing, mark as failed.
    if sections["error_details"] is None or sections["corrected_code"] is None:
        # Check if the raw text actually contains keywords, indicating AI tried but format was wrong
        if "error details" in response_text.lower() or "corrected code" in response_text.lower():
             parsing_successful = False # Mark as failed if keywords present but parsing didn't get them
        # If keywords aren't even present, maybe the AI response was validly short (e.g., no errors found)
        # We rely on the initial True value unless specific failures occur.


    # If all sections failed to parse AND the response wasn't empty
    if response_text and not sections["error_details"] and not sections["corrected_code"] and not sections["suggestions"]:
         parsing_successful = False # Definitely failed if response has text but nothing was extracted


    return sections, parsing_successful


# --- Streamlit App UI ---
# (Keep the UI section largely the same, including the input text_area with its key)
st.set_page_config(page_title="BugFix AI", page_icon="🐞")

st.title("🐞 BugFix AI")
st.write("Paste your code with errors below. The AI will analyze it, provide error details, suggest corrections, and offer enhancement ideas.")

user_code = st.text_area(
    "Enter your code here:",
    height=250,
    placeholder="def my_function(a, b):\n  print(a + b)\n\nmy_function(5, 'hello') # Error here!",
    key="user_code_input"
)

analyze_button = st.button("Analyze and Fix Code", disabled=not genai_configured)


# --- Processing and Output ---

if analyze_button and user_code and genai_configured:
    with st.spinner("AI is analyzing your code... 🧠"):
        try:
            # --- Refined Prompt ---
            prompt = f"""
            Analyze the following code snippet for errors. Provide a detailed explanation of the errors found.
            Then, provide the corrected version of the code.
            Finally, offer suggestions for potential enhancements or best practices related to the code.

            **IMPORTANT:** Structure your response *exactly* like this, using these specific markdown headings:

            ## Error Details
            [Your detailed explanation of errors found. Be clear and concise.]

            ## Corrected Code
            ```python
            [ONLY the corrected version of the original input code goes here. Do NOT add example usage or other code blocks in this section.]
            ```

            ## Suggestions
            [Your suggestions for enhancement or best practices. Explain your points clearly. Avoid putting full code examples here unless absolutely necessary for illustration, and if so, keep them brief.]

            ---
            Code to analyze:
            ```python
            {user_code}
            ```
            ---
            """

            # Send prompt to the Gemini model
            response = model.generate_content(prompt)
            ai_response_text = ""
            parsing_successful = False
            parsed_sections = {} # Initialize

            if response.parts:
                ai_response_text = response.text
                parsed_sections, parsing_successful = parse_ai_response(ai_response_text)

                st.subheader("Analysis Results:")

                # Display Error Details
                st.markdown("### 🧐 Error Details")
                details = parsed_sections.get("error_details", "[No error details extracted.]")
                if "[Parsing Error:" in details:
                    st.warning(details)
                elif details == "[No error details extracted.]" and not parsing_successful:
                     st.info("Could not extract error details. The AI response might be malformed.")
                elif details:
                    st.markdown(details)
                else: # Should not happen with .get default, but as fallback
                    st.info("No error details provided or extracted.")


                # Display Corrected Code
                st.markdown("### ✨ Corrected Code")
                code = parsed_sections.get("corrected_code")
                if code and "[Parsing Error:" in code:
                    st.warning(code)
                elif code:
                     st.code(code, language="python") # Assume python
                else:
                     st.info("No corrected code provided or extracted.")
                     if not parsing_successful:
                         st.warning("Could not extract corrected code. The AI response might be malformed.")


                # Display Suggestions
                st.markdown("### 💡 Suggestions for Enhancement")
                suggestions = parsed_sections.get("suggestions", "[No suggestions provided or extracted.]")
                if "[Parsing Error:" in suggestions:
                    st.warning(suggestions)
                elif suggestions:
                    st.markdown(suggestions)
                else:
                    st.info("No suggestions provided or extracted.")


                # --- Consolidated Debug Output ---
                if not parsing_successful and ai_response_text:
                    st.warning("⚠️ The AI response format didn't perfectly match expectations, so parsing might be incomplete. Displaying the raw AI output below for reference.")
                    st.text_area("Raw AI Response", ai_response_text, height=200, key="debug_raw_response_area")

            else:
                 # Handle blocked response
                 st.error("❌ The AI response was empty or blocked (potentially due to safety filters).")
                 try:
                     st.json({"prompt_feedback": response.prompt_feedback})
                 except Exception:
                     st.write("Could not retrieve prompt feedback.")

        except Exception as e:
            st.error(f"An error occurred during AI interaction or processing: {e}")
            st.exception(e)

elif analyze_button and not user_code:
    st.warning("Please enter some code to analyze.")
elif analyze_button and not genai_configured:
     st.error("AI is not configured. Please set up the Google API Key.")

