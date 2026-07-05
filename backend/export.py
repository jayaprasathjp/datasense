import json
import os

transcript_path = r"C:\Users\sanja\.gemini\antigravity\brain\6bf9ad9e-f1cc-4e4b-bdfe-ebbab01b2543\.system_generated\logs\transcript.jsonl"
export_path = r"d:\crazy-projects\gen_ai_cohort_hackathon\datasense\conversation_export.md"

with open(export_path, 'w', encoding='utf-8') as out_f:
    out_f.write("# Conversation Export\n\n")
    if not os.path.exists(transcript_path):
        out_f.write("Transcript file not found.\n")
    else:
        with open(transcript_path, 'r', encoding='utf-8') as in_f:
            for line in in_f:
                try:
                    data = json.loads(line)
                    sender = data.get('source', 'UNKNOWN')
                    content = data.get('content', '')
                    
                    if sender == 'USER_EXPLICIT' or sender == 'USER':
                        out_f.write(f"## USER\n\n{content}\n\n")
                    elif sender == 'MODEL' or sender == 'AGENT':
                        out_f.write(f"## AGENT\n\n{content}\n\n")
                        # Include tool calls if any
                        tool_calls = data.get('tool_calls', [])
                        for tc in tool_calls:
                            tc_name = tc.get('name', 'tool')
                            tc_args = tc.get('arguments', {})
                            out_f.write(f"**Tool Call: {tc_name}**\n`json\n{json.dumps(tc_args, indent=2)}\n`\n\n")
                    elif sender == 'SYSTEM':
                        # System messages are usually too long and noisy, let's include only tool responses if they are short
                        type_ = data.get('type')
                        if type_ == 'TOOL_RESPONSE':
                            out_f.write(f"**Tool Response**\n`\n{content[:1000]}{'...' if len(content) > 1000 else ''}\n`\n\n")
                except json.JSONDecodeError:
                    pass

print("Export completed:", export_path)
