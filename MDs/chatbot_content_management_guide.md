# Chatbot Content Management Guide

This guide covers all aspects of managing chatbot content, including uploading files, editing content, and using the automatic summarization feature.

## Table of Contents

1. [Content Upload Process](#content-upload-process)
2. [Supported File Types](#supported-file-types)
3. [Multi-File Upload](#multi-file-upload)
4. [Content Preview](#content-preview)
5. [Character Limits](#character-limits)
6. [GPT-Based Summarization](#gpt-based-summarization)
7. [Content Editing](#content-editing)
8. [Technical Implementation](#technical-implementation)

## Content Upload Process

The chatbot system allows administrators to upload content from various file types. This content serves as the knowledge base for the chatbot's responses.

### Basic Upload Flow

1. Navigate to the Admin Dashboard
2. Go to the "Create New Chatbot" tab
3. Enter the required metadata:
   - Chatbot ID (unique identifier)
   - Display Name (user-friendly name)
   - Description
   - Program Category
   - Intro Message
   - Daily Question Quota
   - Character Limit
4. Select files for upload
5. Preview content (optional but recommended)
6. Create the chatbot

### Backend Processing

When files are uploaded, the system:
1. Extracts text from each file using appropriate libraries
2. Combines extracted content into a single knowledge base
3. Checks against character limits
4. Applies summarization if necessary and enabled
5. Stores the processed content in the database

## Supported File Types

The system can extract text from multiple file formats:

| File Type | Extensions | Library Used | Notes |
|-----------|------------|--------------|-------|
| Text files | .txt | Native Python | Simple UTF-8 text extraction |
| PDF documents | .pdf | PyPDF2 | Extracts text from all pages |
| Word documents | .docx | python-docx | Extracts paragraph text |
| PowerPoint | .ppt, .pptx | python-pptx | Extracts text from shapes |

If primary libraries are unavailable, the system falls back to `textract` for broader file format support.

## Multi-File Upload

The system supports uploading multiple files simultaneously, which are processed and combined into a single knowledge base.

### Implementation Details

- Files can be selected via a file dialog or drag-and-drop
- Content from all files is combined with newline separators
- Files are processed in the order they are uploaded
- The system provides a visual preview of uploaded files

```javascript
// File upload handling logic
for (let i = 0; i < uploadedFiles.length; i++) {
    formData.append('files', uploadedFiles[i]);
}
```

## Content Preview

Before finalizing a chatbot, you can preview the extracted content:

1. Select files for upload
2. Click "Preview Content"
3. Review the extracted text
4. Make any necessary edits
5. View character count and limits
6. Apply changes and create the chatbot

The preview feature provides:
- Individual file previews with character counts
- Combined content view
- Character limit warnings
- Editable text for final adjustments

## Character Limits

Character limits prevent excessive token usage when interfacing with LLM APIs.

### Default Limits
- Default: 50,000 characters
- Minimum: 50,000 characters
- Maximum: 100,000 characters

### Impact on Costs
Each character contributes to API costs:
- Approximately 4 characters per token
- Input tokens cost $0.15 per million tokens (for GPT-4o-mini)
- Output tokens cost $0.60 per million tokens (for GPT-4o-mini)

When content exceeds the character limit, there are two options:
1. Enable auto-summarization
2. Increase the character limit

## GPT-Based Summarization

When content exceeds character limits, the system can use GPT to intelligently summarize the content.

### Summarization Process

1. First applies basic cleanup (removing duplicate spaces, newlines)
2. Calculates the target length based on character limit
3. Makes an API call to GPT-4o-mini with specialized prompts
4. Falls back to rule-based summarization if the API call fails

### GPT Summarization Benefits

- Preserves document structure and headings
- Maintains important facts and definitions
- Removes redundancies and verbose explanations
- Achieves higher content preservation than rule-based methods

```python
# GPT-based summarization prompt
system_prompt = f"""You are a text summarization assistant. Summarize the provided text while preserving as much original content as possible. 
The output should be approximately {target_length} characters in length (current text is {current_length} characters).
{prompt_instructions}

IMPORTANT GUIDELINES:
1. Preserve ALL important facts, key concepts, definitions, and essential information without exception
2. Maintain the original document's complete structure, sections, and flow
3. Keep ALL section titles, headers, and subheaders exactly as they appear
4. Remove only clear redundancies and extremely verbose explanations if necessary
5. Do not add any of your own commentary or content not present in the original
6. The summary should aim for approximately {target_length} characters, but prioritize content preservation over length
7. Do not include phrases like "the text discusses" - present the content directly
8. Do not begin with "Here is the summarized content" or similar meta-commentary
9. Preserve ALL technical details, numbers, statistics, names, and specific information
10. The summary must be a comprehensive, cohesive document that captures the full scope of the original
11. Aim to keep at least 50% of the original paragraphs mostly intact"""
```

### Rule-Based Summarization

If GPT summarization fails, the system falls back to rule-based summarization that:

1. Removes duplicate content and boilerplate text
2. Trims appendices, references, and notes sections
3. Preserves introduction and conclusion
4. Identifies and keeps key paragraphs based on keywords
5. Reduces content proportionally if needed

## Content Editing

Existing chatbot content can be edited in several ways:

### Direct Editing
1. Go to the Admin Dashboard
2. Find the chatbot in "Manage Existing Chatbots"
3. Click "Edit Content"
4. Modify the text in the editor
5. Save changes

### Upload New Files
1. In the Edit Content modal, go to "Upload New Files" tab
2. Select new files to add or replace content
3. Choose to append or replace existing content
4. Preview the changes
5. Apply changes and save

### Preview Mode for Editing
The edit preview mode allows:
- Viewing and editing individual file content
- Editing the combined content directly
- Automatic summarization of edited content
- Comparison of character counts before and after edits

## Technical Implementation

### Text Extraction Function

```python
def extract_text_from_file(file_storage):
    """Extracts text from a FileStorage object."""
    filename = secure_filename(file_storage.filename)
    
    content = ""
    try:
        if filename.endswith(".txt"):
            content = file_storage.stream.read().decode("utf-8")
        elif filename.endswith(".pdf"):
            if PYPDF2_AVAILABLE:
                pdf_reader = PyPDF2.PdfReader(file_storage.stream)
                text_parts = [page.extract_text() or "" for page in pdf_reader.pages]
                content = "\n".join(text_parts)
        elif filename.endswith(".docx"):
            if DOCX_AVAILABLE:
                doc = docx.Document(file_storage.stream)
                content = "\n".join([para.text for para in doc.paragraphs])
            elif TEXTRACT_AVAILABLE:
                content = textract.process(filename=filename, 
                                          input_stream=file_storage.stream).decode('utf-8')
        elif filename.endswith(".pptx"):
            if PPTX_AVAILABLE:
                prs = Presentation(file_storage.stream)
                text_parts = []
                for slide in prs.slides:
                    for shape in slide.shapes:
                        if hasattr(shape, "text"):
                            text_parts.append(shape.text)
                content = "\n".join(text_parts)
            elif TEXTRACT_AVAILABLE:
                content = textract.process(filename=filename, 
                                          input_stream=file_storage.stream).decode('utf-8')
        
        file_storage.stream.seek(0)
        return content
    except Exception as e:
        logger.error(f"Error extracting text from {filename}: {e}")
        file_storage.stream.seek(0)
        return ""
```

### Frontend Content Management

The frontend uses JavaScript to manage content and provide real-time feedback:

- Drag-and-drop file upload with visual feedback
- Character counting with progress bars
- Tab-based interface for editing individual files or combined content
- Real-time validation against character limits
- Auto-resize textareas for better editing experience
- Dynamic content summarization requests

### Backend APIs

The system provides these API endpoints for content management:

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/admin/preview_upload` | POST | Preview content before creation |
| `/admin/upload` | POST | Create a new chatbot with content |
| `/admin/get_chatbot_content/<code>` | GET | Retrieve content for editing |
| `/admin/update_chatbot_content` | POST | Save updated content |

## Best Practices

1. **File Selection**: Choose files with clear, well-formatted content
2. **Content Organization**: Upload related files together
3. **Manual Cleanup**: Use the preview feature to clean up content before finalizing
4. **Character Management**: Keep content under the character limit to avoid summarization
5. **Test After Changes**: Always test the chatbot after updating content
6. **Preserve Structure**: Maintain headings and document structure for better responses
7. **Remove Irrelevant Content**: Delete boilerplate text, confidentiality notices, and other irrelevant content
8. **Combine Related Content**: Group related information from multiple sources
9. **Use Summarization Wisely**: Enable auto-summarize for large documents, but review the results 