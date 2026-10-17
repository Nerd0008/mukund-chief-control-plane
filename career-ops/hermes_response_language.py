"""Owner response policy: no model calls, translation, or repeated tool execution."""
import hashlib,re

FAILURE=("I blocked a response because it was generated in Chinese instead of English. "
         "I have not rerun the task or repeated any writes. The response needs an English summary.")

def chinese_requested(message):
    # Current owner instruction only, never conversation history or quoted tool output.
    text=str(message)
    text=re.sub(r"```.*?```", "", text, flags=re.S)
    text="\n".join(line for line in text.splitlines() if not line.lstrip().startswith('>'))
    if re.search(r"(?i)\b(?:don't|do not|never|stop|avoid)\b.{0,45}\b(?:Chinese|Mandarin)\b",text):return False
    return bool(re.search(r"(?im)^\s*(?:please\s+)?(?:answer|reply|respond|write|speak|translate)(?:\s+\w+){0,5}\s+(?:in|into)\s+(?:Chinese|Mandarin)\b",text))

def unexpected_chinese(text):
    if not isinstance(text,str):return False
    prose=re.sub(r"```.*?```", "", text, flags=re.S)
    # Preserve explicit quotes/code and incidental names. Catch prose even in mixed answers.
    prose="\n".join(line for line in prose.splitlines() if not line.lstrip().startswith('>'))
    for line in prose.splitlines():
        han=sum('\u3400'<=c<='\u9fff' for c in line)
        if han>=8 and han/max(1,sum(c.isalpha() for c in line))>=0.20:return True
    return False

def checked_text(text,allow_chinese=False):
    return FAILURE if not allow_chinese and unexpected_chinese(text) else text

def checked_result(result,allow_chinese=False):
    if not isinstance(result,dict):return result
    original=result.get('final_response')
    if not allow_chinese and unexpected_chinese(original):
        result=dict(result)
        result['final_response']=FAILURE
        result['response_language']={'status':'blocked','expected':'English',
            'original_sha256':hashlib.sha256(original.encode('utf-8')).hexdigest()}
    return result

class BufferedText:
    """Validate complete stream segments, including single-character deltas, before display."""
    def __init__(self,callback,allow_chinese=False):
        self.callback=callback;self.allow=allow_chinese;self.parts=[]
    def __call__(self,text):
        if text is None:
            self.flush();return self.callback(None)
        self.parts.append(text)
    def flush(self):
        if self.parts:
            text=''.join(self.parts);self.parts=[]
            self.callback(checked_text(text,self.allow))
