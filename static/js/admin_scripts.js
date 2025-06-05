document.addEventListener('DOMContentLoaded', function() {
    // Force scroll to the top of the page on load
    window.scrollTo(0, 0);

    // Debug mode - uncomment to enable detailed debug info
    const DEBUG = true;
    
    function debugLog(msg) {
        if (DEBUG) {
            console.log(msg);
            const debugElem = document.getElementById('debug-info');
            if (debugElem) {
                debugElem.style.display = 'block';
                debugElem.innerHTML += msg + '\n';
            }
        }
    }
    
    // =============================================
    // 파일 업로드 관련 변수와 요소들
    // =============================================
    const fileInput = document.getElementById('file');
    const browseFilesBtn = document.getElementById('browseFilesBtn');
    const dropArea = document.getElementById('dropArea');
    const fileList = document.getElementById('fileList');
    const fileCounter = document.getElementById('fileCounter');
    const fileActions = document.getElementById('fileActions');
    const clearAllFilesBtn = document.getElementById('clearAllFilesBtn');
    
    // 파일 저장을 위한 배열
    let uploadedFiles = [];
    
    // File size formatter
    function formatFileSize(bytes) {
        if (bytes === 0) return '0 Bytes';
        const k = 1024;
        const sizes = ['Bytes', 'KB', 'MB', 'GB'];
        const i = Math.floor(Math.log(bytes) / Math.log(k));
        return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
    }
    
    // 중복 파일 체크 함수
    function isDuplicateFile(file, filesArray) {
        return filesArray.some(f => 
            f.name === file.name && 
            f.size === file.size && 
            f.lastModified === file.lastModified
        );
    }
    
    // 파일 목록 업데이트 함수
    function updateFileList() {
        if (uploadedFiles.length > 0) {
            fileList.innerHTML = '';
            fileList.style.display = 'block';
            fileActions.style.display = 'flex !important';
            
            uploadedFiles.forEach((file, index) => {
                const fileItem = document.createElement('div');
                fileItem.className = 'file-item';
                fileItem.innerHTML = `
                    <div class="file-info">
                        <div class="file-name">${file.name}</div>
                        <div class="file-size">${formatFileSize(file.size)}</div>
                    </div>
                    <div class="file-actions">
                        <button type="button" class="remove-file" data-index="${index}">
                            <i class="bi bi-x-circle"></i>
                        </button>
                    </div>
                `;
                fileList.appendChild(fileItem);
            });
            
            fileCounter.textContent = `${uploadedFiles.length} file${uploadedFiles.length > 1 ? 's' : ''} selected`;
        } else {
            fileList.style.display = 'none';
            fileActions.style.display = 'none !important';
            fileCounter.textContent = '';
        }
    }
    
    // 파일 추가 함수
    function addFiles(files) {
        Array.from(files).forEach(file => {
            if (!isDuplicateFile(file, uploadedFiles)) {
                uploadedFiles.push(file);
            }
        });
        updateFileList();
    }
    
    // Set aria-valuenow for accessibility
    const progressBars = document.querySelectorAll('.progress-bar');
    progressBars.forEach(function(bar) {
        // Extract width percentage from the style attribute if it exists
        const style = bar.getAttribute('style') || '';
        const widthMatch = style.match(/width:\s*([\d.]+)%/);
        if (widthMatch && widthMatch[1]) {
            bar.setAttribute('aria-valuenow', widthMatch[1]);
        }
    });
    
    // Upload form submission
    document.getElementById('submit-btn').addEventListener('click', function() {
        const form = document.getElementById('upload-form');
        const formData = new FormData(form);
        
        // Check if we have edited content in the preview section
        const previewSection = document.getElementById('preview-section');
        const isPreviewVisible = previewSection && previewSection.style.display !== 'none';
        
        console.log("Submit button clicked");
        console.log("Preview section visible:", isPreviewVisible);
        console.log("Files uploaded:", uploadedFiles.length);
        
        // Get auto summarize option
        const autoSummarize = document.getElementById('auto_summarize').checked;
        formData.append('auto_summarize', autoSummarize.toString());
        
        // Always remove original file fields from form data to avoid duplication
        formData.delete('file');
        
        // When preview is visible, use the combined preview content
        if (isPreviewVisible) {
            const combinedPreview = document.getElementById('combined-preview');
            if (combinedPreview && combinedPreview.value) {
                const combinedContent = combinedPreview.value;
                console.log(`Using edited content from preview. Length: ${combinedContent.length} chars`);
                
                // IMPORTANT: Remove any files to ensure we only use the edited content
                // This prevents the server from trying to process both sources
                formData.delete('files');
                
                // Add the edited content as the definitive source
                formData.append('combined_content', combinedContent);
                formData.append('use_edited_content', 'true');
                
                console.log("Removed original files from submission and using only combined_content");
            } else {
                console.warn("Preview section is visible but combined-preview element not found or empty");
                alert('Error: Preview content is empty. Please make sure you have content to submit.');
                return;
            }
        } else if (uploadedFiles.length > 0) {
            // Only use the original files if no preview content exists but files are available
            console.log("No preview section found, using original files");
            for (let i = 0; i < uploadedFiles.length; i++) {
                formData.append('files', uploadedFiles[i]);
            }
        } else {
            // No files and no preview content
            alert('Please select at least one file or use the preview feature to add content');
            return;
        }
        
        // Show loading state
        this.disabled = true;
        this.textContent = 'Uploading...';
        
        // Debug form data being submitted
        console.log("Form data keys being submitted:");
        for (const key of formData.keys()) {
            if (key === 'combined_content') {
                console.log(`${key}: [content length: ${formData.get(key).length} chars]`);
            } else {
                console.log(`${key}: ${formData.get(key)}`);
            }
        }
        
        // Debug URL
        console.log("Upload URL:", window.adminUrls.upload);
        const uploadUrl = window.adminUrls.upload || '/admin/upload';
        console.log("Using URL:", uploadUrl);
        
        fetch(uploadUrl, {
            method: 'POST',
            body: formData
        })
        .then(response => {
            console.log('Response status:', response.status);
            console.log('Response URL:', response.url);
            
            // Always try to parse JSON first
            return response.json().then(data => {
                if (response.ok) {
                    // Success response
                    return { success: true, data: data };
                } else {
                    // Error response with JSON data
                    console.log('Error data received:', data);
                    return { success: false, error: data };
                }
            }).catch(jsonError => {
                console.error('Failed to parse JSON response:', jsonError);
                // If JSON parsing fails, return generic error
                return { 
                    success: false, 
                    error: { 
                        error: `HTTP ${response.status}: ${response.statusText}`,
                        message: 'Server returned invalid response format'
                    }
                };
            });
        })
        .then(result => {
            if (result.success) {
                // Success case
                window.location.href = window.adminUrls.adminBase + "?message=" + encodeURIComponent('The chatbot has been successfully created') + "&message_type=success";
            } else {
                // Error case
                const errorData = result.error;
                let errorMessage;
                
                if (errorData.error === "Content too long" && errorData.warning) {
                    errorMessage = 'Content too long: ' + errorData.warning + 
                                 '\n\nCurrent length: ' + (errorData.content_length || 'unknown').toLocaleString() + ' characters' +
                                 '\nLimit: ' + (errorData.char_limit || 'unknown').toLocaleString() + ' characters' +
                                 '\n\nPlease reduce content or enable auto-summarize.';
                } else {
                    errorMessage = 'Error: ' + (errorData.error || errorData.message || 'Could not create chatbot.');
                }
                
                alert(errorMessage);
                this.disabled = false;
                this.textContent = 'Create Chatbot';
            }
        })
        .catch(networkError => {
            console.error('Network error:', networkError);
            alert('Network error: ' + networkError.message);
            this.disabled = false;
            this.textContent = 'Create Chatbot';
        });
    });
    
    // Preview button handler
    document.getElementById('preview-btn').addEventListener('click', function() {
        if (uploadedFiles.length === 0) {
            alert('Please select at least one file');
            return;
        }
        
        const form = document.getElementById('upload-form');
        const formData = new FormData(form);
        
        // Get auto-summarize option and add it to form data
        const autoSummarize = document.getElementById('auto_summarize').checked;
        formData.append('auto_summarize', autoSummarize.toString());
        
        // Add files from uploadedFiles array
        for (let i = 0; i < uploadedFiles.length; i++) {
            formData.append('files', uploadedFiles[i]);
        }
        // Remove the single 'file' field to avoid duplication
        formData.delete('file');
        
        // Show loading state
        this.disabled = true;
        this.textContent = 'Generating Preview...';
        
        fetch(window.adminUrls.previewUpload, {
            method: 'POST',
            body: formData
        })
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                // Enable submit button after preview
                document.getElementById('submit-btn').disabled = false;
                
                // Show preview section
                document.getElementById('preview-section').style.display = 'block';
                
                // Update character counts
                document.getElementById('total-char-count').textContent = data.total_char_count.toLocaleString();
                document.getElementById('char-limit').textContent = data.char_limit.toLocaleString();
                document.getElementById('combined-char-count').textContent = data.total_char_count.toLocaleString();
                
                // Update progress bar
                const charLimit = parseInt(data.char_limit);
                const percentage = Math.min((data.total_char_count / charLimit) * 100, 100);
                const progressBar = document.getElementById('char-progress-bar');
                progressBar.style.width = percentage + '%';
                progressBar.setAttribute('aria-valuenow', percentage);
                progressBar.textContent = Math.round(percentage) + '%';
                
                // Color the progress bar based on percentage
                if (percentage > 90) {
                    progressBar.className = 'progress-bar bg-danger';
                } else if (percentage > 75) {
                    progressBar.className = 'progress-bar bg-warning';
                } else {
                    progressBar.className = 'progress-bar bg-success';
                }
                
                // Show warning or success message based on summarization result
                const limitWarning = document.getElementById('limit-warning');
                if (data.exceeds_limit) {
                    limitWarning.style.display = 'block';
                    limitWarning.className = 'alert alert-danger mt-3';
                    document.getElementById('limit-warning-message').textContent = data.warning;
                } else if (data.was_summarized) {
                    limitWarning.style.display = 'block';
                    limitWarning.className = 'alert alert-success mt-3';
                    document.getElementById('limit-warning-message').textContent = data.warning;
                } else {
                    limitWarning.style.display = 'none';
                }
                
                // Show combined preview in textarea
                document.getElementById('combined-preview').value = data.combined_preview;
                
                // Create file previews with editable textareas
                const filePreviewsContainer = document.getElementById('file-previews');
                filePreviewsContainer.innerHTML = '';
                
                data.files.forEach((file, index) => {
                    const fileCard = document.createElement('div');
                    fileCard.className = 'card mb-3';
                    fileCard.innerHTML = `
                        <div class="card-header d-flex justify-content-between align-items-center">
                            <span>${file.filename}</span>
                            <span class="badge bg-secondary">${file.char_count.toLocaleString()} characters</span>
                        </div>
                        <div class="card-body">
                            <div class="d-flex justify-content-between align-items-center mb-2">
                                <label for="file-content-${index}" class="form-label mb-0">Extracted text:</label>
                                <div class="char-counter file-char-counter" id="file-char-counter-${index}">
                                    <span id="file-char-count-${index}">${file.char_count.toLocaleString()}</span> characters
                                </div>
                            </div>
                            <textarea id="file-content-${index}" class="form-control file-content-editor" data-original-length="${file.char_count}">${file.content}</textarea>
                        </div>
                    `;
                    filePreviewsContainer.appendChild(fileCard);
                    
                    // Add event listener to update character count for this file
                    const textarea = fileCard.querySelector(`#file-content-${index}`);
                    const charCounter = fileCard.querySelector(`#file-char-count-${index}`);
                    
                    textarea.addEventListener('input', function() {
                        const newCount = this.value.length;
                        charCounter.textContent = newCount.toLocaleString();
                        
                        // Update badge in header
                        const badge = fileCard.querySelector('.badge');
                        badge.textContent = newCount.toLocaleString() + ' characters';
                        
                        // Check if exceeding original length significantly
                        const originalLength = parseInt(this.dataset.originalLength);
                        if (newCount > originalLength * 1.5) {
                            badge.className = 'badge bg-warning';
                        } else if (newCount < originalLength * 0.5) {
                            badge.className = 'badge bg-info';
                        } else {
                            badge.className = 'badge bg-secondary';
                        }
                    });
                });
                
                // Add input event listener for live character count on combined-preview
                const combinedPreviewTextarea = document.getElementById('combined-preview');
                combinedPreviewTextarea.addEventListener('input', function() {
                    const newCount = this.value.length;
                    document.getElementById('combined-char-count').textContent = newCount.toLocaleString();
                    
                    // Update total count as well
                    document.getElementById('total-char-count').textContent = newCount.toLocaleString();
                    
                    // Update progress bar
                    const percentage = Math.min((newCount / charLimit) * 100, 100);
                    progressBar.style.width = percentage + '%';
                    progressBar.setAttribute('aria-valuenow', percentage);
                    progressBar.textContent = Math.round(percentage) + '%';
                    
                    // Color the progress bar based on percentage
                    if (percentage > 90) {
                        progressBar.className = 'progress-bar bg-danger';
                    } else if (percentage > 75) {
                        progressBar.className = 'progress-bar bg-warning';
                    } else {
                        progressBar.className = 'progress-bar bg-success';
                    }
                    
                    // Check if exceeds limit and update warning
                    if (newCount > charLimit) {
                        limitWarning.style.display = 'block';
                        limitWarning.className = 'alert alert-danger mt-3';
                        document.getElementById('limit-warning-message').innerHTML = 
                            `Content exceeds the ${charLimit.toLocaleString()} character limit (currently ${newCount.toLocaleString()} characters). 
                            You may need to reduce the content or increase the limit.`;
                    } else {
                        if (limitWarning.classList.contains('alert-danger')) {
                            limitWarning.style.display = 'none';
                        }
                    }
                });
                
                // Add event listener to update combined content
                document.getElementById('update-combined-content').addEventListener('click', function() {
                    // Determine which tab is active
                    const isFilesTabActive = document.getElementById('files-tab').classList.contains('active');
                    
                    if (isFilesTabActive) {
                        // Collect all individual file contents
                        const contentParts = [];
                        data.files.forEach((file, index) => {
                            const textarea = document.getElementById(`file-content-${index}`);
                            if (textarea) {
                                contentParts.push(textarea.value);
                            }
                        });
                        const updatedContent = contentParts.join('\n\n');
                        
                        // Update combined preview
                        document.getElementById('combined-preview').value = updatedContent;
                        
                        // Update character counts
                        const newCount = updatedContent.length;
                        document.getElementById('combined-char-count').textContent = newCount.toLocaleString();
                        document.getElementById('total-char-count').textContent = newCount.toLocaleString();
                        
                        // Update progress bar
                        const percentage = Math.min((newCount / charLimit) * 100, 100);
                        progressBar.style.width = percentage + '%';
                        progressBar.setAttribute('aria-valuenow', percentage);
                        progressBar.textContent = Math.round(percentage) + '%';
                        
                        // Check if exceeds limit
                        if (newCount > charLimit) {
                            limitWarning.style.display = 'block';
                            limitWarning.className = 'alert alert-danger mt-3';
                            document.getElementById('limit-warning-message').innerHTML = 
                                `Content exceeds the ${charLimit.toLocaleString()} character limit (currently ${newCount.toLocaleString()} characters). 
                                Consider using "Summarize Now" or manually edit to reduce content.`;
                        } else {
                            if (limitWarning.classList.contains('alert-danger')) {
                                limitWarning.style.display = 'none';
                            }
                        }
                    }
                    
                    // Show status
                    document.getElementById('update-combined-content-status').style.display = 'inline';
                    setTimeout(() => {
                        document.getElementById('update-combined-content-status').style.display = 'none';
                    }, 2000);
                    
                    // Highlight the Create Chatbot button
                    document.getElementById('submit-btn').classList.add('btn-success');
                    document.getElementById('submit-btn').classList.remove('btn-primary');
                    document.getElementById('submit-btn').innerHTML = '<i class="bi bi-plus-circle"></i> <strong>Create Chatbot</strong>';
                });
                
                // Scroll to preview section
                document.getElementById('preview-section').scrollIntoView({ behavior: 'smooth' });
            } else {
                alert('Error: ' + (data.error || 'Could not generate preview.'));
            }
            
            // Reset button state
            this.disabled = false;
            this.textContent = 'Preview Content';
        })
        .catch(error => {
            alert('Network error: ' + error);
            this.disabled = false;
            this.textContent = 'Preview Content';
        });
    });
    
    // Delete chatbot
    document.querySelectorAll('.delete-btn').forEach(function(btn) {
        btn.addEventListener('click', function() {
            const chatbotName = this.getAttribute('data-chatbot-name');
            if (confirm('Are you sure you want to delete the chatbot?')) {
                const formData = new FormData();
                formData.append('chatbot_name', chatbotName);
                
                const xhr = new XMLHttpRequest();
                xhr.open('POST', window.adminUrls.deleteChatbot, true);
                
                xhr.onload = function() {
                    if (xhr.status >= 200 && xhr.status < 300) {
                        window.location.href = window.adminUrls.adminBase + "?message=" + encodeURIComponent('The chatbot has been successfully deleted') + "&message_type=success";
                    } else {
                        alert('Error: Could not delete chatbot');
                    }
                };
                
                xhr.send(formData);
            }
        });
    });
    
    // Update description
    document.querySelectorAll('.update-desc-btn').forEach(function(btn) {
        btn.addEventListener('click', function() {
            const parentForm = this.closest('.update-desc-form');
            const chatbotName = parentForm.querySelector('.chatbot-name').value;
            const description = parentForm.querySelector('.description-field').value;
            
            const formData = new FormData();
            formData.append('chatbot_name', chatbotName);
            formData.append('description', description);
            
            const xhr = new XMLHttpRequest();
            xhr.open('POST', window.adminUrls.updateDescription, true);
            
            xhr.onload = function() {
                if (xhr.status >= 200 && xhr.status < 300) {
                    window.location.href = window.adminUrls.adminBase + "?message=" + encodeURIComponent('Description has been updated') + "&message_type=success";
                } else {
                    alert('Error: Could not update description');
                }
            };
            
            xhr.send(formData);
        });
    });
    
    // Restore chatbot
    document.querySelectorAll('.restore-btn').forEach(function(btn) {
        btn.addEventListener('click', function() {
            const chatbotName = this.getAttribute('data-chatbot-name');
            
            const formData = new FormData();
            formData.append('chatbot_name', chatbotName);
            
            const xhr = new XMLHttpRequest();
            xhr.open('POST', window.adminUrls.restoreChatbot, true);
            
            xhr.onload = function() {
                if (xhr.status >= 200 && xhr.status < 300) {
                    window.location.href = window.adminUrls.adminBase + "?message=" + encodeURIComponent('The chatbot has been successfully restored') + "&message_type=success";
                } else {
                    alert('Error: Could not restore chatbot');
                }
            };
            
            xhr.send(formData);
        });
    });
    
    // Permanent delete chatbot
    document.querySelectorAll('.permanent-delete-btn').forEach(function(btn) {
        btn.addEventListener('click', function() {
            const chatbotName = this.getAttribute('data-chatbot-name');
            if (confirm('WARNING: This will permanently delete the chatbot and cannot be undone. Are you sure?')) {
                const formData = new FormData();
                formData.append('chatbot_name', chatbotName);
                
                const xhr = new XMLHttpRequest();
                xhr.open('POST', window.adminUrls.permanentDeleteChatbot, true);
                
                xhr.onload = function() {
                    if (xhr.status >= 200 && xhr.status < 300) {
                        window.location.href = window.adminUrls.adminBase + "?message=" + encodeURIComponent('The chatbot has been permanently deleted') + "&message_type=success";
                    } else {
                        alert('Error: Could not permanently delete chatbot');
                    }
                };
                
                xhr.send(formData);
            }
        });
    });

    // Edit Content button handler
    document.querySelectorAll('.edit-content-btn').forEach(function(btn) {
        btn.addEventListener('click', function() {
            const chatbotCode = this.getAttribute('data-chatbot-code');
            const chatbotDisplayName = this.getAttribute('data-chatbot-display-name');
            
            const modalTitle = document.getElementById('editContentModalLabel');
            const contentTextarea = document.getElementById('chatbotContentTextarea');
            const hiddenChatbotNameInput = document.getElementById('editChatbotNameInput');
            const editContentModal = new bootstrap.Modal(document.getElementById('editContentModal'));

            modalTitle.textContent = 'Edit Content for ' + chatbotDisplayName;
            contentTextarea.value = 'Loading content...';
            hiddenChatbotNameInput.value = chatbotCode;
            editContentModal.show();

            console.log("Fetching content for chatbot:", chatbotCode);
            
            // Use fetch API instead of XMLHttpRequest for better error handling
            fetch(window.adminUrls.getChatbotContent + encodeURIComponent(chatbotCode))
                .then(response => {
                    if (!response.ok) {
                        throw new Error(`Error: ${response.status} ${response.statusText}`);
                    }
                    return response.json();
                })
                .then(data => {
                    if (data.success) {
                        contentTextarea.value = data.content;
                        document.getElementById('editCharLimit').value = data.char_limit;
                        document.getElementById('charLimitDisplay').textContent = data.char_limit.toLocaleString();
                        document.getElementById('editSystemPromptGuidelines').value = data.system_prompt_guidelines || '';
                        updateCharCount();
                    } else {
                        contentTextarea.value = 'Error: ' + (data.error || 'Failed to load content');
                        console.error('Server returned error:', data.error);
                    }
                })
                .catch(error => {
                    contentTextarea.value = 'Error fetching content: ' + error.message;
                    console.error('Fetch error:', error);
                });
        });
    });
    
    // Update character count
    function updateCharCount() {
        const content = document.getElementById('chatbotContentTextarea').value;
        const count = content.length;
        document.getElementById('currentCharCount').textContent = count.toLocaleString();
    }

    // Add character count update on input
    document.getElementById('chatbotContentTextarea').addEventListener('input', updateCharCount);

    // Save Content button handler
    document.getElementById('saveContentChangesBtn').addEventListener('click', function() {
        const chatbotCode = document.getElementById('editChatbotNameInput').value;
        const charLimit = document.getElementById('editCharLimit').value;
        const appendContent = document.getElementById('appendContent').checked;
        const autoSummarize = document.getElementById('editAutoSummarize').checked;
        const systemPromptGuidelines = document.getElementById('editSystemPromptGuidelines').value;
        const saveButton = this;
        
        if (!chatbotCode) {
            alert('Error: Cannot identify chatbot. Please reload the page and try again.');
            return;
        }
        
        // Get current content based on active tab
        let newContent = "";
        const editPreviewSection = document.getElementById('edit-preview-section');
        const editCombinedPreview = document.getElementById('edit-combined-preview');
        const chatbotContentTextarea = document.getElementById('chatbotContentTextarea');
        
        // Log what content we're using
        console.log("Save button clicked for chatbot:", chatbotCode);
        
        // Case 1: Using preview content if available and visible
        if (editPreviewSection && editPreviewSection.style.display !== 'none' && 
            editCombinedPreview && editCombinedPreview.value) {
            newContent = editCombinedPreview.value;
            console.log("Using edited content from preview tab, length:", newContent.length);
        } 
        // Case 2: Using main text area content
        else if (chatbotContentTextarea && chatbotContentTextarea.value) {
            newContent = chatbotContentTextarea.value;
            console.log("Using content from main textarea, length:", newContent.length);
        }
        else {
            alert('Error: No content found to save. Please add some content first.');
            return;
        }
        
        if (!newContent.trim()) {
            alert('Error: Cannot save empty content. Please add some content first.');
            return;
        }
        
        const formData = new FormData();
        formData.append('chatbot_code', chatbotCode);
        formData.append('content', newContent);
        formData.append('char_limit', charLimit);
        formData.append('append_content', 'false'); // When editing, we're replacing content, not appending
        formData.append('system_prompt_guidelines', systemPromptGuidelines);
        
        // Only enable auto-summarize when content exceeds limit
        const contentExceedsLimit = newContent.length > parseInt(charLimit);
        formData.append('auto_summarize', (autoSummarize && contentExceedsLimit).toString());
        
        // Show warning if content exceeds limit and auto-summarize is not enabled
        if (contentExceedsLimit && !autoSummarize) {
            if (!confirm(`Content length (${newContent.length.toLocaleString()} characters) exceeds the character limit (${parseInt(charLimit).toLocaleString()} characters).\n\nContinue without auto-summarization? You may get an error if you don't enable auto-summarize.`)) {
                return;
            }
        }
        
        formData.append('use_edited_content', 'true'); // Always treat this as edited content
        
        // Visual feedback - show a loading overlay
        saveButton.disabled = true;
        saveButton.innerHTML = '<span class="spinner-border spinner-border-sm" role="status" aria-hidden="true"></span> Saving...';
        
        // Create a status message element for continuous feedback
        let statusMsg = document.createElement('div');
        statusMsg.className = 'alert alert-info mt-2';
        statusMsg.innerHTML = '<i class="bi bi-info-circle"></i> Saving changes...';
        saveButton.parentNode.appendChild(statusMsg);

        fetch(window.adminUrls.updateChatbotContent, {
            method: 'POST',
            body: formData
        })
        .then(response => {
            // First check if the response is ok
            console.log("Server response status:", response.status);
            return response.json();
        })
        .then(data => {
            console.log("Server response:", data);
            if (data.success) {
                // Success - update status and redirect after a short delay
                statusMsg.className = 'alert alert-success mt-2';
                
                // Check if content was summarized
                if (data.was_summarized) {
                    statusMsg.innerHTML = `
                        <i class="bi bi-check-circle"></i> <strong>Content saved successfully!</strong>
                        <p>${data.warning || 'Content was automatically summarized to fit within the character limit.'}</p>
                        <div class="progress mt-2 mb-2" style="height: 20px;">
                            <div class="progress-bar bg-success" role="progressbar" 
                                style="width: ${data.summarization_stats.percent_reduced}%;" 
                                aria-valuenow="${data.summarization_stats.percent_reduced}" 
                                aria-valuemin="0" aria-valuemax="100">
                                ${data.summarization_stats.percent_reduced}% Reduced
                            </div>
                        </div>
                        <div class="d-flex justify-content-between text-muted small">
                            <span>Original: ${data.summarization_stats.original_length.toLocaleString()} chars</span>
                            <span>Final: ${data.summarization_stats.final_length.toLocaleString()} chars</span>
                        </div>
                        <p class="mt-2">Redirecting...</p>
                    `;
                } else {
                    statusMsg.innerHTML = '<i class="bi bi-check-circle"></i> Content saved successfully! Redirecting...';
                }
                
                setTimeout(() => {
                    const editContentModal = bootstrap.Modal.getInstance(document.getElementById('editContentModal'));
                    if (editContentModal) {
                        editContentModal.hide();
                    }
                    window.location.href = window.adminUrls.adminBase + "?message=" + encodeURIComponent('Content has been updated successfully!') + "&message_type=success";
                }, 2000);
            } else {
                // Server returned success:false with an error message
                statusMsg.className = 'alert alert-danger mt-2';
                
                if (data.error === "Content too long") {
                    // Handle character limit error specially
                    statusMsg.innerHTML = `<i class="bi bi-exclamation-triangle"></i> <strong>Content too long:</strong> ${data.warning || 'The content exceeds the character limit.'}`;
                    
                    // Show character limit details
                    let limitDetails = document.createElement('div');
                    limitDetails.innerHTML = `
                        <div class="mt-2">
                            <p>Current length: <strong>${Number(data.content_length).toLocaleString()}</strong> characters</p>
                            <p>Character limit: <strong>${Number(data.char_limit).toLocaleString()}</strong> characters</p>
                            <div class="d-flex gap-2 mt-2">
                                <button class="btn btn-sm btn-warning increase-limit-btn">Increase Limit</button>
                                <button class="btn btn-sm btn-primary enable-auto-summarize-btn">Enable Auto-Summarize</button>
                            </div>
                        </div>
                    `;
                    statusMsg.appendChild(limitDetails);
                    
                    // Add event handlers for the action buttons
                    statusMsg.querySelector('.increase-limit-btn').addEventListener('click', function() {
                        const newLimit = Math.min(parseInt(charLimit) + 10000, 200000);
                        document.getElementById('editCharLimit').value = newLimit;
                        document.getElementById('charLimitDisplay').textContent = newLimit.toLocaleString();
                        statusMsg.remove();
                        // Re-enable the save button
                        saveButton.disabled = false;
                        saveButton.innerHTML = '<i class="bi bi-save"></i> Save Changes';
                    });
                    
                    statusMsg.querySelector('.enable-auto-summarize-btn').addEventListener('click', function() {
                        document.getElementById('editAutoSummarize').checked = true;
                        statusMsg.remove();
                        // Re-enable the save button and click it again
                        saveButton.disabled = false;
                        saveButton.innerHTML = '<i class="bi bi-save"></i> Save Changes';
                        saveButton.click();
                    });
                } else {
                    // Generic error
                    statusMsg.innerHTML = `<i class="bi bi-exclamation-triangle"></i> <strong>Error:</strong> ${data.error || 'Could not save content.'}<br>
                                                 <small>Please try again or check the console for more details.</small>`;
                    console.error('Error saving content:', data);
                }
                
                // Re-enable the save button for retry
                saveButton.disabled = false;
                saveButton.innerHTML = '<i class="bi bi-save"></i> Save Changes';
            }
        })
        .catch(error => {
            // Network or parsing error
            statusMsg.className = 'alert alert-danger mt-2';
            statusMsg.innerHTML = `<i class="bi bi-exclamation-triangle"></i> <strong>Error:</strong> ${error.message}<br>
                                         <small>Please check your network connection and try again.</small>`;
            console.error('Error saving content:', error);
            
            // Re-enable the save button
            saveButton.disabled = false;
            saveButton.innerHTML = '<i class="bi bi-save"></i> Save Changes';
        });
    });

    // Add event listener for the edit increase limit button
    document.getElementById('edit-increase-limit-btn').addEventListener('click', function() {
        const currentLimit = parseInt(document.getElementById('editCharLimit').value);
        const newLimit = Math.min(currentLimit + 10000, 200000);
        document.getElementById('editCharLimit').value = newLimit;
        document.getElementById('charLimitDisplay').textContent = newLimit.toLocaleString();
        bootstrap.Modal.getInstance(document.getElementById('editWarningModal')).hide();
        
        // Also add an option to try automatic summarization
        document.getElementById('editAutoSummarize').checked = true;
        
        document.getElementById('saveContentChangesBtn').click();
    });

    // Update quota
    document.querySelectorAll('.update-quota-btn').forEach(function(btn) {
        btn.addEventListener('click', function() {
            const parentForm = this.closest('.update-quota-form');
            const chatbotName = parentForm.querySelector('.chatbot-name').value;
            const quota = parentForm.querySelector('.quota-field').value;

            if (!quota || parseInt(quota) < 1) {
                alert('Please enter a valid quota (must be 1 or greater).');
                return;
            }

            // Show a brief loading indicator on the button
            const originalText = this.innerHTML;
            this.innerHTML = '<i class="bi bi-hourglass-split"></i> Updating...';
            this.disabled = true;

            fetch(window.adminUrls.updateQuota, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    chatbot_code: chatbotName,
                    quota: parseInt(quota)
                })
            })
            .then(response => response.json())
            .then(data => {
                // Reset button state
                this.innerHTML = originalText;
                this.disabled = false;
                
                if (data.success) {
                    // Show temporary success message next to the button
                    const successMsg = document.createElement('span');
                    successMsg.className = 'text-success ms-2';
                    successMsg.innerHTML = '<i class="bi bi-check-circle"></i> Updated!';
                    this.parentNode.appendChild(successMsg);
                    
                    // Remove success message after 2 seconds
                    setTimeout(() => {
                        successMsg.remove();
                    }, 2000);
                } else {
                    alert('Error: ' + (data.error || 'Could not update quota.'));
                }
            })
            .catch(error => {
                // Reset button state
                this.innerHTML = originalText;
                this.disabled = false;
                alert('Network error while updating quota. Please try again.');
            });
        });
    });

    // Update LO Root IDs
    document.querySelectorAll('.update-lo-root-btn').forEach(function(btn) {
        btn.addEventListener('click', function() {
            const parentForm = this.closest('.update-lo-root-form');
            const chatbotName = parentForm.querySelector('.chatbot-name').value;
            const loRootIds = parentForm.querySelector('.lo-root-field').value.trim();

            // Show a brief loading indicator on the button
            const originalText = this.innerHTML;
            this.innerHTML = '<i class="bi bi-hourglass-split"></i> Updating...';
            this.disabled = true;

            fetch('/admin/update_lo_root_ids', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    chatbot_code: chatbotName,
                    lo_root_ids: loRootIds
                })
            })
            .then(response => response.json())
            .then(data => {
                // Reset button state
                this.innerHTML = originalText;
                this.disabled = false;
                
                if (data.success) {
                    // Show temporary success message next to the button
                    const successMsg = document.createElement('span');
                    successMsg.className = 'text-success ms-2';
                    successMsg.innerHTML = '<i class="bi bi-check-circle"></i> Access Control Updated!';
                    this.parentNode.appendChild(successMsg);
                    
                    // Remove success message after 3 seconds
                    setTimeout(() => {
                        successMsg.remove();
                    }, 3000);
                    
                    // Show additional info about access control
                    if (loRootIds) {
                        console.log(`Access control updated for ${chatbotName}: ${loRootIds.split(';').length} LO Root IDs`);
                    } else {
                        console.log(`Access control removed for ${chatbotName}: All users can now access`);
                    }
                } else {
                    alert('Error: ' + (data.error || 'Could not update LO Root IDs.'));
                }
            })
            .catch(error => {
                // Reset button state
                this.innerHTML = originalText;
                this.disabled = false;
                alert('Network error while updating LO Root IDs. Please try again.');
                console.error('Error updating LO Root IDs:', error);
            });
        });
    });

    // Preview Files button handler in edit modal
    document.getElementById('editPreviewBtn').addEventListener('click', function() {
        const fileInput = document.getElementById('editFiles');
        if (!fileInput.files.length) {
            alert('Please select at least one file to preview');
            return;
        }
        
        const formData = new FormData();
        // Add files to form data
        for (let i = 0; i < fileInput.files.length; i++) {
            formData.append('files', fileInput.files[i]);
        }
        
        // Add character limit
        const charLimit = document.getElementById('editCharLimit').value;
        formData.append('char_limit', charLimit);
        
        // Add auto-summarize option
        const autoSummarize = document.getElementById('editAutoSummarize').checked;
        formData.append('auto_summarize', autoSummarize.toString());
        
        // Add current content and append flag for a more accurate preview
        const currentContent = document.getElementById('chatbotContentTextarea').value;
        const appendContent = document.getElementById('appendContent').checked;
        if (appendContent && currentContent) {
            formData.append('current_content', currentContent);
            formData.append('append_content', 'true');
        }
        
        // Show loading state
        this.disabled = true;
        this.textContent = 'Generating Preview...';
        
        fetch(window.adminUrls.previewUpload, {
            method: 'POST',
            body: formData
        })
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                // Show preview section
                document.getElementById('edit-preview-section').style.display = 'block';
                
                // Update character counts
                document.getElementById('edit-total-char-count').textContent = data.total_char_count.toLocaleString();
                document.getElementById('edit-char-limit').textContent = data.char_limit.toLocaleString();
                
                // Show warning if limit exceeded or success message if summarized
                const limitWarning = document.getElementById('edit-limit-warning');
                if (data.exceeds_limit) {
                    limitWarning.style.display = 'block';
                    limitWarning.className = 'alert alert-danger';
                    document.getElementById('edit-limit-warning-message').textContent = data.warning;
                } else if (data.was_summarized) {
                    limitWarning.style.display = 'block';
                    limitWarning.className = 'alert alert-success';
                    document.getElementById('edit-limit-warning-message').textContent = data.warning;
                } else {
                    limitWarning.style.display = 'none';
                }
                
                // Show combined preview in textarea
                document.getElementById('edit-combined-preview').value = data.combined_preview;
                
                // Create file previews with editable textareas
                const filePreviewsContainer = document.getElementById('edit-file-previews');
                filePreviewsContainer.innerHTML = '';
                
                data.files.forEach((file, index) => {
                    const fileCard = document.createElement('div');
                    fileCard.className = 'card mb-3';
                    fileCard.innerHTML = `
                        <div class="card-header d-flex justify-content-between align-items-center">
                            <span>${file.filename}</span>
                            <span class="badge bg-secondary">${file.char_count.toLocaleString()} characters</span>
                        </div>
                        <div class="card-body">
                            <label for="edit-file-content-${index}" class="form-label">Extracted text:</label>
                            <textarea id="edit-file-content-${index}" class="form-control" style="white-space: pre-wrap; min-height: 300px; max-height: 600px; resize: vertical; font-family: monospace;">${file.content}</textarea>
                        </div>
                    `;
                    filePreviewsContainer.appendChild(fileCard);
                });
                
                // Add event listeners to update buttons for individual files
                document.querySelectorAll('.edit-update-file-content').forEach(button => {
                    button.addEventListener('click', function() {
                        const fileIndex = this.getAttribute('data-file-index');
                        const updatedContent = document.getElementById(`edit-file-content-${fileIndex}`).value;
                        data.files[fileIndex].content = updatedContent;
                        
                        // Recalculate character count
                        data.files[fileIndex].char_count = updatedContent.length;
                        this.parentElement.parentElement.parentElement.querySelector('.badge').textContent = 
                            `${updatedContent.length.toLocaleString()} characters`;
                        
                        // Show status
                        document.getElementById(`edit-update-file-status-${fileIndex}`).style.display = 'inline';
                        setTimeout(() => {
                            document.getElementById(`edit-update-file-status-${fileIndex}`).style.display = 'none';
                        }, 2000);
                    });
                });
                
                // Add event listener to update combined content and sync with textarea
                document.getElementById('update-edit-combined-content').addEventListener('click', function() {
                    console.log("Edit modal: Apply Changes button clicked");
                    
                    // Collect all individual file contents first
                    let updatedContents = [];
                    data.files.forEach((file, index) => {
                        const textarea = document.getElementById(`edit-file-content-${index}`);
                        if (textarea) {
                            updatedContents.push(textarea.value);
                            console.log(`Edit modal: File ${index} (${file.filename}): ${textarea.value.length} chars`);
                        }
                    });
                    
                    // Use either the combined edited content or individual file contents
                    const activeTab = document.querySelector('#editPreviewTabs .nav-link.active');
                    let updatedCombinedContent;
                    
                    if (activeTab && activeTab.id === 'edit-combined-tab') {
                        // Using the combined editor
                        updatedCombinedContent = document.getElementById('edit-combined-preview').value;
                        console.log(`Edit modal: Using combined editor content (${updatedCombinedContent.length} chars)`);
                    } else {
                        // Using individual file editors
                        updatedCombinedContent = updatedContents.join('\n\n');
                        document.getElementById('edit-combined-preview').value = updatedCombinedContent;
                        console.log(`Edit modal: Using individual files content (${updatedCombinedContent.length} chars)`);
                    }
                    
                    // Update textarea with edited content
                    document.getElementById('chatbotContentTextarea').value = updatedCombinedContent;
                    updateCharCount(); // Call the existing function to update character count display
                    
                    // Update character count info
                    const newCount = updatedCombinedContent.length;
                    document.getElementById('edit-total-char-count').textContent = newCount.toLocaleString();
                    console.log(`Edit modal: New content length: ${newCount} chars`);
                    
                    // Check if exceeds limit
                    const charLimit = parseInt(document.getElementById('edit-char-limit').textContent.replace(/,/g, ''));
                    const limitWarning = document.getElementById('edit-limit-warning');
                    
                    console.log(`Edit modal: Checking limits: ${newCount} chars vs ${charLimit} limit`);
                    
                    if (newCount > charLimit) {
                        console.log("Edit modal: Content exceeds limit after changes applied");
                        limitWarning.style.display = 'block';
                        limitWarning.className = 'alert alert-danger';
                        document.getElementById('edit-limit-warning-message').textContent = 
                            `Content exceeds ${charLimit.toLocaleString()} characters (current: ${newCount.toLocaleString()}). You may need to summarize again.`;
                        
                        // If auto-summarize is checked, offer to summarize now
                        if (document.getElementById('editAutoSummarize').checked) {
                            const shouldSummarize = confirm(`Content exceeds character limit. Would you like to automatically summarize it now?`);
                            if (shouldSummarize) {
                                // Re-trigger the preview with the current content to invoke auto-summarization
                                const summaryFormData = new FormData();
                                summaryFormData.append('current_content', updatedCombinedContent);
                                summaryFormData.append('append_content', 'false');
                                summaryFormData.append('char_limit', charLimit);
                                summaryFormData.append('auto_summarize', 'true');
                                
                                console.log("Edit modal: Requesting auto-summarization");
                                
                                fetch(window.adminUrls.previewUpload, {
                                    method: 'POST',
                                    body: summaryFormData
                                })
                                .then(response => response.json())
                                .then(summaryData => {
                                    if (summaryData.success && summaryData.was_summarized) {
                                        console.log(`Edit modal: Summarization successful. New length: ${summaryData.total_char_count} chars`);
                                        document.getElementById('edit-combined-preview').value = summaryData.combined_preview;
                                        document.getElementById('chatbotContentTextarea').value = summaryData.combined_preview;
                                        document.getElementById('edit-total-char-count').textContent = summaryData.total_char_count.toLocaleString();
                                        
                                        // Show success message
                                        limitWarning.className = 'alert alert-success';
                                        document.getElementById('edit-limit-warning-message').textContent = summaryData.warning;
                                        updateCharCount();
                                    }
                                });
                            }
                        }
                        
                    } else {
                        limitWarning.style.display = 'none';
                    }
                    
                    // Show status
                    document.getElementById('update-edit-combined-content-status').style.display = 'inline';
                    setTimeout(() => {
                        document.getElementById('update-edit-combined-content-status').style.display = 'none';
                    }, 2000);
                    
                    // Highlight the Save Changes button to guide the user to the next step
                    document.getElementById('saveContentChangesBtn').classList.add('btn-success');
                    document.getElementById('saveContentChangesBtn').classList.remove('btn-primary');
                    document.getElementById('saveContentChangesBtn').innerHTML = '<i class="bi bi-save"></i> <strong>Save Changes</strong> <i class="bi bi-arrow-right"></i>';
                    document.getElementById('saveContentChangesBtn').classList.add('shadow-pulse');
                    // Scroll to make the button visible
                    document.getElementById('saveContentChangesBtn').scrollIntoView({ behavior: 'smooth', block: 'center' });
                    
                    // Switch to main content tab to show updated content
                    document.getElementById('current-content-tab').click();
                });
                
                // Scroll to preview section
                document.getElementById('edit-preview-section').scrollIntoView({ behavior: 'smooth' });
            } else {
                alert('Error: ' + (data.error || 'Could not preview files.'));
            }
            
            // Reset button state
            this.disabled = false;
            this.textContent = 'Preview Files';
        })
        .catch(error => {
            alert('Network error: ' + error);
            this.disabled = false;
            this.textContent = 'Preview Files';
        });
    });

    // Improved handling for intro message editing with live preview
    document.querySelectorAll('.update-intro-form').forEach(form => {
        const introField = form.querySelector('.intro-field');
        const previewText = form.querySelector('.preview-text');
        const resetBtn = form.querySelector('.reset-intro-btn');
        const chatbotName = form.querySelector('.chatbot-name').value;
        
        // Get quota from the same chatbot card
        const chatbotCard = form.closest('.chatbot-card');
        const quotaField = chatbotCard.querySelector('.quota-field');
        const displayName = chatbotCard.querySelector('.card-header h5').textContent.trim();
        
        // Update preview when intro message is edited
        introField.addEventListener('input', function() {
            updateIntroPreview(this.value, displayName, quotaField.value);
        });
        
        // Also update preview when quota changes
        quotaField.addEventListener('change', function() {
            updateIntroPreview(introField.value, displayName, this.value);
        });
        
        // Reset to default intro message
        resetBtn.addEventListener('click', function() {
            const defaultIntro = "Hi, I am the {program} chatbot. I can answer up to {quota} question(s) related to this program per day.";
            introField.value = defaultIntro;
            updateIntroPreview(defaultIntro, displayName, quotaField.value);
        });
        
        // Function to update the preview
        function updateIntroPreview(text, program, quota) {
            let preview = text.replace('{program}', program).replace('{quota}', quota);
            previewText.textContent = preview;
        }
        
        // Initialize preview
        updateIntroPreview(introField.value, displayName, quotaField.value);
    });

    // Update the Create New Chatbot form as well with intro message preview
    const createForm = document.getElementById('upload-form');
    if (createForm) {
        const introField = createForm.querySelector('#intro_message');
        const quotaField = createForm.querySelector('#default_quota');
        const displayNameField = createForm.querySelector('#display_name');
        
        if (introField && displayNameField) {
            // Add a preview section after the intro message field
            const previewDiv = document.createElement('div');
            previewDiv.className = 'card bg-light mb-3';
            previewDiv.innerHTML = `
                <div class="card-body py-2">
                    <div class="intro-message-preview">
                        <strong>Preview:</strong> <span id="create-preview-text"></span>
                    </div>
                </div>
            `;
            introField.parentNode.insertBefore(previewDiv, introField.nextSibling);
            
            const previewText = document.getElementById('create-preview-text');
            
            // Update preview when any field changes
            function updateCreatePreview() {
                const displayName = displayNameField.value || "[Program Name]";
                const quota = quotaField ? quotaField.value : "3";
                let preview = introField.value.replace('{program}', displayName).replace('{quota}', quota);
                previewText.textContent = preview;
            }
            
            introField.addEventListener('input', updateCreatePreview);
            if (displayNameField) displayNameField.addEventListener('input', updateCreatePreview);
            if (quotaField) quotaField.addEventListener('input', updateCreatePreview);
            
            // Add reset button to intro message field
            const helpText = introField.nextElementSibling;
            if (helpText && helpText.classList.contains('form-text')) {
                const resetBtn = document.createElement('button');
                resetBtn.type = 'button';
                resetBtn.className = 'btn btn-sm btn-link text-decoration-none p-0 ms-2';
                resetBtn.textContent = 'Reset to default';
                resetBtn.addEventListener('click', function() {
                    const defaultIntro = "Hi, I am the {program} chatbot. I can answer up to {quota} question(s) related to this program per day.";
                    introField.value = defaultIntro;
                    updateCreatePreview();
                });
                helpText.appendChild(resetBtn);
            }
            
            // Initialize preview
            updateCreatePreview();
        }
    }

    // Setup event listeners for intro message updates
    document.querySelectorAll('.update-intro-btn').forEach(button => {
        button.addEventListener('click', function() {
            const form = this.closest('.update-intro-form');
            const chatbotName = form.querySelector('.chatbot-name').value;
            const introMessage = form.querySelector('.intro-field').value.trim();
            
            if (!introMessage) {
                alert('Please enter an intro message');
                return;
            }
            
            // Show a brief loading indicator on the button
            const originalText = this.innerHTML;
            this.innerHTML = '<i class="bi bi-hourglass-split"></i> Updating...';
            this.disabled = true;
            
            fetch(window.adminUrls.updateIntroMessage, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    chatbot_code: chatbotName,
                    intro_message: introMessage
                }),
            })
            .then(response => response.json())
            .then(data => {
                // Reset button state
                this.innerHTML = originalText;
                this.disabled = false;
                
                if (data.success) {
                    // Show temporary success message next to the button
                    const successMsg = document.createElement('span');
                    successMsg.className = 'text-success ms-2';
                    successMsg.innerHTML = '<i class="bi bi-check-circle"></i> Updated!';
                    this.parentNode.appendChild(successMsg);
                    
                    // Remove success message after 2 seconds
                    setTimeout(() => {
                        successMsg.remove();
                    }, 2000);
                } else {
                    alert('Error updating intro message: ' + data.error);
                }
            })
            .catch(error => {
                // Reset button state
                this.innerHTML = originalText;
                this.disabled = false;
                alert('Network error while updating intro message. Please try again.');
            });
        });
    });

    // Function to show alert messages
    function showAlert(message, type) {
        const alertDiv = document.createElement('div');
        alertDiv.className = `alert alert-${type} alert-dismissible fade show`;
        alertDiv.innerHTML = `
            ${message}
            <button type="button" class="btn-close" data-bs-dismiss="alert" aria-label="Close"></button>
        `;
        
        // Find a good place to insert the alert
        const container = document.querySelector('.card-body');
        if (container) {
            container.insertAdjacentElement('afterbegin', alertDiv);
            
            // Auto dismiss after 3 seconds
            setTimeout(() => {
                alertDiv.classList.remove('show');
                setTimeout(() => alertDiv.remove(), 1500);
            }, 3000);
        }
    }

    // Set styles for progress bars that use data-width attribute
    document.querySelectorAll('.progress-bar[data-width]').forEach(function(bar) {
        const width = bar.getAttribute('data-width');
        if (width) {
            bar.style.width = width + '%';
            bar.setAttribute('aria-valuenow', width);
        }
    });

    // Auto-activate Data Management > Conversation Logs tab if anchor is present
    if (window.location.hash) {
        const hash = window.location.hash.replace('#', '');
        if (hash === 'data-mgmt-content-convo-logs') {
            // Activate Data Management main tab
            var mainTab = document.querySelector('button[data-bs-target="#data-mgmt-content"]');
            if (mainTab) mainTab.click();
            // Activate Conversation Logs sub-tab after a short delay
            setTimeout(function() {
                var subTab = document.querySelector('button[data-bs-target="#convo-logs"]');
                if (subTab) subTab.click();
            }, 200);
        }
    }

    // Add handler for "Summarize Now" button in main creation form
    document.getElementById('summarize-now-btn').addEventListener('click', function() {
        const charLimit = parseInt(document.getElementById('char-limit').textContent.replace(/,/g, ''));
        const currentContent = document.getElementById('combined-preview').value;
        
        if (!currentContent) {
            alert('No content to summarize.');
            return;
        }
        
        // Show loading state
        this.disabled = true;
        this.querySelector('.summarize-btn-text').style.display = 'none';
        this.querySelector('.summarize-spinner').style.display = 'inline-block';
        this.classList.remove('btn-warning');
        this.classList.add('btn-secondary');
        
        const formData = new FormData();
        formData.append('current_content', currentContent);
        formData.append('char_limit', charLimit);
        formData.append('auto_summarize', 'true');
        
        // Update message to indicate summarization is in progress
        const limitWarning = document.getElementById('limit-warning');
        const originalMessage = document.getElementById('limit-warning-message').textContent;
        document.getElementById('limit-warning-message').innerHTML = 
            `<div class="alert alert-info mb-0">
                <p><i class="bi bi-hourglass-split"></i> <strong>Processing...</strong></p>
                <p>Summarizing content. This may take a moment for large documents.</p>
            </div>`;
        
        fetch(window.adminUrls.previewUpload, {
            method: 'POST',
            body: formData
        })
        .then(response => response.json())
        .then(data => {
            if (data.success && data.was_summarized) {
                // Update the content
                document.getElementById('combined-preview').value = data.combined_preview;
                
                // NEW: Update individual file textareas if data.files is available
                if (data.files && Array.isArray(data.files)) {
                    data.files.forEach((file, index) => {
                        const individualFileTextarea = document.getElementById(`file-content-${index}`);
                        if (individualFileTextarea) {
                            individualFileTextarea.value = file.content;
                            console.log(`Updated file-content-${index} with summarized part, new length: ${file.content.length}`);
                        }
                    });
                }
                
                // Update count
                document.getElementById('total-char-count').textContent = data.total_char_count.toLocaleString();
                
                // Create detailed success message
                const stats = data.summarization_stats;
                let summaryHtml = `
                    <div class="alert alert-success mb-0">
                        <p><i class="bi bi-check-circle"></i> <strong>Summarization Complete!</strong></p>
                        <p>${data.warning}</p>
                        <div class="progress mt-2 mb-2" style="height: 20px;">
                            <div class="progress-bar bg-success" role="progressbar" 
                                 style="width: ${stats.percent_reduced}%;" 
                                 aria-valuenow="${stats.percent_reduced}" 
                                 aria-valuemin="0" aria-valuemax="100">
                                ${stats.percent_reduced}% Reduced
                            </div>
                        </div>
                        <div class="d-flex justify-content-between text-muted small">
                            <span>Original: ${stats.original_length.toLocaleString()} chars</span>
                            <span>Final: ${stats.final_length.toLocaleString()} chars</span>
                        </div>
                    </div>`;
                
                // Show success message
                limitWarning.style.display = 'block';
                limitWarning.className = 'alert alert-success';
                document.getElementById('limit-warning-message').innerHTML = summaryHtml;
                
                // Hide the unnecessary options after successful summarization
                const optionsUl = limitWarning.querySelector('ul');
                if (optionsUl) {
                    optionsUl.style.display = 'none';
                }
                const summarizeBtnItself = document.getElementById('summarize-now-btn');
                if (summarizeBtnItself) {
                    summarizeBtnItself.style.display = 'none';
                }
                
                // Highlight the Apply Changes button to guide the user to the next step
                document.getElementById('update-combined-content').classList.add('btn-success');
                document.getElementById('update-combined-content').classList.remove('btn-primary');
                document.getElementById('update-combined-content').innerHTML = '<i class="bi bi-check2-all"></i> <strong>Apply Changes</strong> <i class="bi bi-arrow-right"></i>';
                document.getElementById('update-combined-content').classList.add('shadow-pulse');
                
                // Switch to combined tab to show the result
                document.getElementById('combined-tab').click();
            } else {
                // Show error message
                limitWarning.className = 'alert alert-danger';
                document.getElementById('limit-warning-message').textContent = data.error || data.warning || 'No changes made.';
            }
            
            // Reset button state
            this.disabled = false;
            this.querySelector('.summarize-btn-text').style.display = 'inline-block';
            this.querySelector('.summarize-spinner').style.display = 'none';
            this.classList.remove('btn-secondary');
            this.classList.add('btn-warning');
        })
        .catch(error => {
            alert('Network error: ' + error);
            // Reset button state
            this.disabled = false;
            this.querySelector('.summarize-btn-text').style.display = 'inline-block';
            this.querySelector('.summarize-spinner').style.display = 'none';
            this.classList.remove('btn-secondary');
            this.classList.add('btn-warning');
            // Restore original message
            document.getElementById('limit-warning-message').textContent = originalMessage;
        });
    });
    
    // Add handler for "Summarize Now" button in edit mode
    const editSummarizeBtn = document.getElementById('edit-summarize-now-btn');
    if (editSummarizeBtn) {
        editSummarizeBtn.addEventListener('click', function() {
            const charLimit = parseInt(document.getElementById('edit-char-limit').textContent.replace(/,/g, ''));
            const currentContent = document.getElementById('edit-combined-preview') 
                ? document.getElementById('edit-combined-preview').value 
                : document.getElementById('chatbotContentTextarea').value;
            
            if (!currentContent) {
                alert('No content to summarize.');
                return;
            }
            
            // Show loading state
            this.disabled = true;
            this.querySelector('.summarize-btn-text').style.display = 'none';
            this.querySelector('.summarize-spinner').style.display = 'inline-block';
            this.classList.remove('btn-warning');
            this.classList.add('btn-secondary');
            
            // Update message to indicate summarization is in progress
            const limitWarning = document.getElementById('edit-limit-warning');
            const originalMessage = document.getElementById('edit-limit-warning-message').textContent;
            document.getElementById('edit-limit-warning-message').innerHTML = 
                `<div class="alert alert-info mb-0">
                    <p><i class="bi bi-hourglass-split"></i> <strong>Processing...</strong></p>
                    <p>Summarizing content. This may take a moment for large documents. Please be patient.</p>
                </div>`;
            
            const formData = new FormData();
            formData.append('current_content', currentContent);
            formData.append('char_limit', charLimit);
            formData.append('auto_summarize', 'true');
            
            fetch(window.adminUrls.previewUpload, {
                method: 'POST',
                body: formData
            })
            .then(response => response.json())
            .then(data => {
                if (data.success && data.was_summarized) {
                    // Update the content in both places
                    if (document.getElementById('edit-combined-preview')) {
                        document.getElementById('edit-combined-preview').value = data.combined_preview;
                    }
                    document.getElementById('chatbotContentTextarea').value = data.combined_preview;
                    
                    // Update count and status
                    document.getElementById('edit-total-char-count').textContent = data.total_char_count.toLocaleString();
                    updateCharCount(); // This updates currentCharCount for chatbotContentTextarea
                    
                    // Create detailed success message
                    const stats = data.summarization_stats;
                    let summaryHtml = `
                        <div class="alert alert-success mb-0">
                            <p><i class="bi bi-check-circle"></i> <strong>Summarization Complete!</strong></p>
                            <p>${data.warning}</p>
                            <div class="progress mt-2 mb-2" style="height: 20px;">
                                <div class="progress-bar bg-success" role="progressbar" 
                                     style="width: ${stats.percent_reduced}%;" 
                                     aria-valuenow="${stats.percent_reduced}" 
                                     aria-valuemin="0" aria-valuemax="100">
                                    ${stats.percent_reduced}% Reduced
                                </div>
                            </div>
                            <div class="d-flex justify-content-between text-muted small">
                                <span>Original: ${stats.original_length.toLocaleString()} chars</span>
                                <span>Final: ${stats.final_length.toLocaleString()} chars</span>
                            </div>
                        </div>`;
                    
                    const editLimitWarning = document.getElementById('edit-limit-warning');
                    editLimitWarning.style.display = 'block'; // Show the warning area
                    editLimitWarning.className = 'alert alert-success'; // Style as success
                    document.getElementById('edit-limit-warning-message').innerHTML = summaryHtml; // Populate with success details

                    // Hide the "Summarize Now" button in the edit modal as summarization is complete
                    const editSummarizeBtnItself = document.getElementById('edit-summarize-now-btn');
                    if (editSummarizeBtnItself) {
                        const btnContainer = editSummarizeBtnItself.closest('.mt-2'); // Find parent div with class 'mt-2'
                        if (btnContainer) {
                            btnContainer.style.display = 'none';
                        } else {
                            editSummarizeBtnItself.style.display = 'none'; // Fallback if container not found
                        }
                    }
                    
                    // Highlight the Apply Changes button in the modal
                    const updateEditCombinedContentBtn = document.getElementById('update-edit-combined-content');
                    if(updateEditCombinedContentBtn){
                        updateEditCombinedContentBtn.classList.add('btn-success', 'shadow-pulse');
                        updateEditCombinedContentBtn.classList.remove('btn-primary');
                        updateEditCombinedContentBtn.innerHTML = '<i class="bi bi-check2-all"></i> <strong>Apply Changes</strong> <i class="bi bi-arrow-right"></i>';
                    }
                    
                    // Switch to main content tab to show updated content
                    document.getElementById('current-content-tab').click();
                } else {
                    // Show error message
                    limitWarning.className = 'alert alert-danger';
                    document.getElementById('edit-limit-warning-message').textContent = data.error || data.warning || 'No changes made.';
                }
                
                // Reset button state
                this.disabled = false;
                this.querySelector('.summarize-btn-text').style.display = 'inline-block';
                this.querySelector('.summarize-spinner').style.display = 'none';
                this.classList.remove('btn-secondary');
                this.classList.add('btn-warning');
            })
            .catch(error => {
                alert('Network error: ' + error);
                // Reset button state
                this.disabled = false;
                this.querySelector('.summarize-btn-text').style.display = 'inline-block';
                this.querySelector('.summarize-spinner').style.display = 'none';
                this.classList.remove('btn-secondary');
                this.classList.add('btn-warning');
                // Restore original message
                document.getElementById('edit-limit-warning-message').textContent = originalMessage;
            });
        });
    }

    // Handle description updates
    document.querySelectorAll('.update-desc-btn').forEach(button => {
        button.addEventListener('click', function() {
            const form = this.closest('.update-desc-form');
            const chatbot = form.querySelector('.chatbot-name').value;
            const description = form.querySelector('.description-field').value;
            
            const formData = new FormData();
            formData.append('chatbot_code', chatbot);
            formData.append('description', description);
            
            this.disabled = true;
            this.innerHTML = '<i class="bi bi-hourglass-split"></i> Updating...';
            
            fetch(window.adminUrls.updateDescription, {
                method: 'POST',
                body: formData
            })
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    this.innerHTML = '<i class="bi bi-check-circle"></i> Done!';
                    setTimeout(() => {
                        this.innerHTML = '<i class="bi bi-check-circle"></i> Update Description';
                        this.disabled = false;
                    }, 2000);
                } else {
                    alert('Error: ' + data.error);
                    this.innerHTML = '<i class="bi bi-check-circle"></i> Update Description';
                    this.disabled = false;
                }
            })
            .catch(error => {
                alert('Network error: ' + error);
                this.innerHTML = '<i class="bi bi-check-circle"></i> Update Description';
                this.disabled = false;
            });
        });
    });
    
    // Handle category updates
    document.querySelectorAll('.update-category-btn').forEach(button => {
        button.addEventListener('click', function() {
            const form = this.closest('.update-category-form');
            const chatbot = form.querySelector('.chatbot-name').value;
            const category = form.querySelector('.category-field').value;
            
            const formData = new FormData();
            formData.append('chatbot_code', chatbot);
            formData.append('category', category);
            
            this.disabled = true;
            this.innerHTML = '<i class="bi bi-hourglass-split"></i> Updating...';
            
            fetch(window.adminUrls.updateCategory, {
                method: 'POST',
                body: formData
            })
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    this.innerHTML = '<i class="bi bi-check-circle"></i> Done!';
                    setTimeout(() => {
                        this.innerHTML = '<i class="bi bi-arrow-clockwise"></i> Update';
                        this.disabled = false;
                    }, 2000);
                } else {
                    alert('Error: ' + data.error);
                    this.innerHTML = '<i class="bi bi-arrow-clockwise"></i> Update';
                    this.disabled = false;
                }
            })
            .catch(error => {
                alert('Network error: ' + error);
                this.innerHTML = '<i class="bi bi-arrow-clockwise"></i> Update';
                this.disabled = false;
            });
        });
    });

    // =============================================
    // 파일 업로드 이벤트 핸들러
    // =============================================
    
    // 브라우즈 버튼 클릭 시 파일 선택 다이얼로그 오픈
    browseFilesBtn.addEventListener('click', () => {
        fileInput.click();
    });
    
    // 파일 선택 시 처리
    fileInput.addEventListener('change', () => {
        if (fileInput.files.length > 0) {
            addFiles(fileInput.files);
        }
        // 파일 선택 후 input 초기화 (같은 파일 다시 선택 가능하게)
        fileInput.value = '';
    });
    
    // 드래그 앤 드롭 이벤트 처리
    ['dragenter', 'dragover', 'dragleave', 'drop'].forEach(eventName => {
        dropArea.addEventListener(eventName, (e) => {
            e.preventDefault();
            e.stopPropagation();
        }, false);
    });
    
    // 드래그 오버 스타일링
    ['dragenter', 'dragover'].forEach(eventName => {
        dropArea.addEventListener(eventName, () => {
            dropArea.classList.add('dragover');
        }, false);
    });
    
    // 드래그 리브/드롭 스타일링 제거
    ['dragleave', 'drop'].forEach(eventName => {
        dropArea.addEventListener(eventName, () => {
            dropArea.classList.remove('dragover');
        }, false);
    });
    
    // 파일 드롭 처리
    dropArea.addEventListener('drop', (e) => {
        if (e.dataTransfer.files.length > 0) {
            addFiles(e.dataTransfer.files);
        }
    }, false);
    
    // 파일 삭제 처리
    fileList.addEventListener('click', (e) => {
        const removeBtn = e.target.closest('.remove-file');
        if (removeBtn) {
            const index = parseInt(removeBtn.dataset.index);
            if (!isNaN(index) && index >= 0 && index < uploadedFiles.length) {
                uploadedFiles.splice(index, 1);
                updateFileList();
            }
        }
    });
    
    // 모든 파일 삭제
    clearAllFilesBtn.addEventListener('click', () => {
        uploadedFiles = [];
        updateFileList();
    });
    
    // =============================================
    // 편집 모달의 파일 업로드 기능
    // =============================================
    const editFileInput = document.getElementById('editFiles');
    const editBrowseFilesBtn = document.getElementById('editBrowseFilesBtn');
    const editDropArea = document.getElementById('editDropArea');
    const editFileList = document.getElementById('editFileList');
    const editFileCounter = document.getElementById('editFileCounter');
    const editFileActions = document.getElementById('editFileActions');
    const editClearAllFilesBtn = document.getElementById('editClearAllFilesBtn');
    
    // 편집 모달용 파일 배열
    let editUploadedFiles = [];
    
    // 편집 모달의 파일 목록 업데이트
    function updateEditFileList() {
        if (editUploadedFiles.length > 0) {
            editFileList.innerHTML = '';
            editFileList.style.display = 'block';
            editFileActions.style.display = 'flex !important';
            
            editUploadedFiles.forEach((file, index) => {
                const fileItem = document.createElement('div');
                fileItem.className = 'file-item';
                fileItem.innerHTML = `
                    <div class="file-info">
                        <div class="file-name">${file.name}</div>
                        <div class="file-size">${formatFileSize(file.size)}</div>
                    </div>
                    <div class="file-actions">
                        <button type="button" class="remove-file" data-index="${index}">
                            <i class="bi bi-x-circle"></i>
                        </button>
                    </div>
                `;
                editFileList.appendChild(fileItem);
            });
            
            editFileCounter.textContent = `${editUploadedFiles.length} file${editUploadedFiles.length > 1 ? 's' : ''} selected`;
        } else {
            editFileList.style.display = 'none';
            editFileActions.style.display = 'none !important';
            editFileCounter.textContent = '';
        }
    }
    
    // 편집 모달에 파일 추가
    function addEditFiles(files) {
        Array.from(files).forEach(file => {
            if (!isDuplicateFile(file, editUploadedFiles)) {
                editUploadedFiles.push(file);
            }
        });
        updateEditFileList();
    }

    // 편집 모달의 파일 업로드 이벤트 핸들러
    if(editBrowseFilesBtn) {
        // 편집 모달의 브라우즈 버튼 클릭 시 파일 선택 다이얼로그 오픈
        editBrowseFilesBtn.addEventListener('click', () => {
            editFileInput.click();
        });
        
        // 편집 모달의 파일 선택 시 처리
        editFileInput.addEventListener('change', () => {
            if (editFileInput.files.length > 0) {
                addEditFiles(editFileInput.files);
            }
            // 파일 선택 후 input 초기화 (같은 파일 다시 선택 가능하게)
            editFileInput.value = '';
        });
        
        // 편집 모달의 드래그 앤 드롭 이벤트 처리
        ['dragenter', 'dragover', 'dragleave', 'drop'].forEach(eventName => {
            editDropArea.addEventListener(eventName, (e) => {
                e.preventDefault();
                e.stopPropagation();
            }, false);
        });
        
        // 편집 모달의 드래그 오버 스타일링
        ['dragenter', 'dragover'].forEach(eventName => {
            editDropArea.addEventListener(eventName, () => {
                editDropArea.classList.add('dragover');
            }, false);
        });
        
        // 편집 모달의 드래그 리브/드롭 스타일링 제거
        ['dragleave', 'drop'].forEach(eventName => {
            editDropArea.addEventListener(eventName, () => {
                editDropArea.classList.remove('dragover');
            }, false);
        });
        
        // 편집 모달의 파일 드롭 처리
        editDropArea.addEventListener('drop', (e) => {
            if (e.dataTransfer.files.length > 0) {
                addEditFiles(e.dataTransfer.files);
            }
        }, false);
        
        // 편집 모달의 파일 삭제 처리
        editFileList.addEventListener('click', (e) => {
            const removeBtn = e.target.closest('.remove-file');
            if (removeBtn) {
                const index = parseInt(removeBtn.dataset.index);
                if (!isNaN(index) && index >= 0 && index < editUploadedFiles.length) {
                    editUploadedFiles.splice(index, 1);
                    updateEditFileList();
                }
            }
        });
        
        // 편집 모달의 모든 파일 삭제
        editClearAllFilesBtn.addEventListener('click', () => {
            editUploadedFiles = [];
            updateEditFileList();
        });
    }

    // "Increase Limit" 버튼 처리
    document.getElementById('increase-limit-btn').addEventListener('click', function() {
        const charLimitElem = document.getElementById('char-limit');
        const currentLimit = parseInt(charLimitElem.textContent.replace(/,/g, ''));
        const charLimitInput = document.getElementById('char_limit');
        
        // 최대 100,000까지 10,000씩 증가
        const newLimit = Math.min(currentLimit + 10000, 200000);
        
        // 입력 필드와 표시 값 모두 업데이트
        charLimitInput.value = newLimit;
        charLimitElem.textContent = newLimit.toLocaleString();
        
        // 프로그레스 바 업데이트
        const totalCharCount = parseInt(document.getElementById('total-char-count').textContent.replace(/,/g, ''));
        const percentage = Math.min((totalCharCount / newLimit) * 100, 100);
        const progressBar = document.getElementById('char-progress-bar');
        progressBar.style.width = percentage + '%';
        progressBar.setAttribute('aria-valuenow', percentage);
        progressBar.textContent = Math.round(percentage) + '%';
        
        // 경고 메시지 처리
        const limitWarning = document.getElementById('limit-warning');
        if (totalCharCount <= newLimit) {
            limitWarning.style.display = 'none';
        } else {
            document.getElementById('limit-warning-message').innerHTML = 
                `Content still exceeds the ${newLimit.toLocaleString()} character limit (currently ${totalCharCount.toLocaleString()} characters). 
                Consider using "Summarize Now" or manually edit to reduce content.`;
        }
        
        // 버튼에 시각적 피드백
        this.textContent = `Increased to ${newLimit.toLocaleString()}`;
        this.classList.add('btn-success');
        this.classList.remove('btn-outline-secondary');
        
        setTimeout(() => {
            this.textContent = 'Increase Limit';
            this.classList.remove('btn-success');
            this.classList.add('btn-outline-secondary');
        }, 2000);
    });

    // Cancel Preview 버튼 처리
    document.querySelectorAll('#cancel-preview-btn, #cancel-preview-btn-bottom').forEach(button => {
        button.addEventListener('click', function() {
            // 프리뷰 섹션 숨기기
            document.getElementById('preview-section').style.display = 'none';
            
            // Submit 버튼 비활성화
            document.getElementById('submit-btn').disabled = true;
            document.getElementById('submit-btn').classList.remove('btn-success');
            document.getElementById('submit-btn').classList.add('btn-primary');
            document.getElementById('submit-btn').innerHTML = '<i class="bi bi-plus-circle"></i> Create Chatbot';
            
            // 스크롤을 업로드 영역으로 이동
            document.getElementById('dropArea').scrollIntoView({ behavior: 'smooth' });
        });
    });
    
    // Apply Changes & Create 버튼 처리 - 수정된 내용을 적용하고 바로 챗봇 생성
    document.getElementById('update-combined-content').addEventListener('click', function() {
        console.log("Apply Changes & Create 버튼 클릭됨");
        
        // 1. 변경사항 적용
        const isFilesTabActive = document.getElementById('files-tab').classList.contains('active');
        const charLimit = parseInt(document.getElementById('char-limit').textContent.replace(/,/g, ''));
        const progressBar = document.getElementById('char-progress-bar');
        const limitWarning = document.getElementById('limit-warning');
        
        let updatedContent = "";
        
        if (isFilesTabActive) {
            // 개별 파일 내용 수집
            const contentParts = [];
            const filePreviews = document.getElementById('file-previews');
            const fileCards = filePreviews.querySelectorAll('.card');
            
            fileCards.forEach((card) => {
                const textarea = card.querySelector('textarea');
                if (textarea) {
                    contentParts.push(textarea.value);
                }
            });
            
            updatedContent = contentParts.join('\n\n');
            
            // Combined Preview 업데이트
            document.getElementById('combined-preview').value = updatedContent;
        } else {
            // Combined 탭에서는 해당 내용 그대로 사용
            updatedContent = document.getElementById('combined-preview').value;
        }
        
        // 캐릭터 수 계산 및 표시 업데이트
        const newCount = updatedContent.length;
        document.getElementById('combined-char-count').textContent = newCount.toLocaleString();
        document.getElementById('total-char-count').textContent = newCount.toLocaleString();
        
        // 프로그레스 바 업데이트
        const percentage = Math.min((newCount / charLimit) * 100, 100);
        progressBar.style.width = percentage + '%';
        progressBar.setAttribute('aria-valuenow', percentage);
        progressBar.textContent = Math.round(percentage) + '%';
        
        // 내용이 제한을 초과하는지 확인
        if (newCount > charLimit) {
            limitWarning.style.display = 'block';
            limitWarning.className = 'alert alert-danger mt-3';
            document.getElementById('limit-warning-message').innerHTML = 
                `Content exceeds the ${charLimit.toLocaleString()} character limit (currently ${newCount.toLocaleString()} characters). 
                Consider using "Summarize Now" or manually edit to reduce content.`;
            
            // 제한 초과 시 생성 막기
            document.getElementById('update-combined-content-status').textContent = 'Changes applied, but cannot create chatbot due to character limit';
            document.getElementById('update-combined-content-status').className = 'text-danger align-self-center';
            document.getElementById('update-combined-content-status').style.display = 'inline';
            
            setTimeout(() => {
                document.getElementById('update-combined-content-status').style.display = 'none';
            }, 3000);
            
            return;
        } else {
            if (limitWarning.classList.contains('alert-danger')) {
                limitWarning.style.display = 'none';
            }
        }
        
        // 2. 상태 메시지 표시
        document.getElementById('update-combined-content-status').textContent = 'Creating chatbot...';
        document.getElementById('update-combined-content-status').className = 'text-info align-self-center';
        document.getElementById('update-combined-content-status').style.display = 'inline';
        
        // 3. Submit 버튼 클릭하여 챗봇 생성 진행
        setTimeout(() => {
            console.log("Submit 버튼 자동 클릭");
            document.getElementById('submit-btn').click();
        }, 500);
    });

    // 편집 모달에서 Cancel Preview 버튼 처리
    document.querySelectorAll('#edit-cancel-preview-btn, #edit-cancel-preview-btn-bottom').forEach(button => {
        if (button) {
            button.addEventListener('click', function() {
                // 편집 미리보기 섹션 숨기기
                document.getElementById('edit-preview-section').style.display = 'none';
                
                // 파일 업로드 영역으로 이동
                document.getElementById('editDropArea').scrollIntoView({ behavior: 'smooth' });
            });
        }
    });
    
    // 편집 모달의 Update 버튼 수정
    const updateEditContentBtn = document.getElementById('update-edit-combined-content');
    if (updateEditContentBtn) {
        updateEditContentBtn.addEventListener('click', function() {
            console.log("Apply Changes & Save 버튼 클릭됨");
            
            // 1. 변경사항 적용
            const isEditFilesTabActive = document.getElementById('edit-files-tab').classList.contains('active');
            const editCharLimit = parseInt(document.getElementById('edit-char-limit').textContent.replace(/,/g, ''));
            
            let updatedContent = "";
            
            if (isEditFilesTabActive) {
                // 개별 파일 내용 수집
                const contentParts = [];
                const filePreviews = document.getElementById('edit-file-previews');
                const fileCards = filePreviews.querySelectorAll('.card');
                
                fileCards.forEach((card) => {
                    const textarea = card.querySelector('textarea');
                    if (textarea) {
                        contentParts.push(textarea.value);
                    }
                });
                
                updatedContent = contentParts.join('\n\n');
                
                // Combined Preview 업데이트
                document.getElementById('edit-combined-preview').value = updatedContent;
            } else {
                // Combined 탭에서는 해당 내용 그대로 사용
                updatedContent = document.getElementById('edit-combined-preview').value;
            }
            
            // 메인 contentTextarea에도 내용 반영
            document.getElementById('chatbotContentTextarea').value = updatedContent;
            
            // 캐릭터 수 업데이트
            const newCount = updatedContent.length;
            if (document.getElementById('edit-combined-char-count')) {
                document.getElementById('edit-combined-char-count').textContent = newCount.toLocaleString();
            }
            if (document.getElementById('edit-total-char-count')) {
                document.getElementById('edit-total-char-count').textContent = newCount.toLocaleString();
            }
            if (document.getElementById('currentCharCount')) {
                document.getElementById('currentCharCount').textContent = newCount.toLocaleString();
            }
            
            // 내용이 제한을 초과하는지 확인
            if (newCount > editCharLimit) {
                document.getElementById('edit-limit-warning').style.display = 'block';
                document.getElementById('edit-limit-warning').className = 'alert alert-danger mt-3';
                document.getElementById('edit-limit-warning-message').innerHTML = 
                    `Content exceeds the ${editCharLimit.toLocaleString()} character limit (currently ${newCount.toLocaleString()} characters). 
                    Consider using "Summarize Now" or manually edit to reduce content.`;
                    
                // 제한 초과 시 저장 막기
                document.getElementById('update-edit-combined-content-status').textContent = 'Changes applied, but cannot save due to character limit';
                document.getElementById('update-edit-combined-content-status').className = 'text-danger';
                document.getElementById('update-edit-combined-content-status').style.display = 'inline';
                
                setTimeout(() => {
                    document.getElementById('update-edit-combined-content-status').style.display = 'none';
                }, 3000);
                
                return;
            }
            
            // 2. 메인 탭으로 전환
            document.getElementById('current-content-tab').click();
            
            // 3. Save Changes 버튼 강조 표시
            document.getElementById('saveContentChangesBtn').classList.add('btn-success');
            document.getElementById('saveContentChangesBtn').classList.remove('btn-primary');
            document.getElementById('saveContentChangesBtn').innerHTML = '<i class="bi bi-save"></i> <strong>Save Changes</strong>';
            
            // 4. 상태 메시지 표시
            document.getElementById('update-edit-combined-content-status').textContent = 'Saving changes...';
            document.getElementById('update-edit-combined-content-status').className = 'text-info';
            document.getElementById('update-edit-combined-content-status').style.display = 'inline';
            
            // 5. Save 버튼 자동 클릭
            setTimeout(() => {
                console.log("Save Changes 버튼 자동 클릭");
                document.getElementById('saveContentChangesBtn').click();
            }, 500);
        }); 
    }

    // JavaScript for filtering conversation logs
    function applyConvoFilters() {
        const searchTerm = document.getElementById('searchConvoInput').value.trim();
        const chatbotCode = document.getElementById('chatbotConvoFilter').value;
        const userId = document.getElementById('userConvoFilter').value;
        
        // Build the URL with the filter parameters
        let url = '/admin?';
        if (searchTerm) url += `search_term=${encodeURIComponent(searchTerm)}&`;
        if (chatbotCode) url += `chatbot_code=${encodeURIComponent(chatbotCode)}&`;
        if (userId) url += `user_id=${encodeURIComponent(userId)}&`;
        
        // Set the hash to ensure we go to the right tab
        url += '#data-mgmt-content-convo-logs';
        
        // Navigate to the filtered URL
        window.location.href = url;
    }
    
    // Setup event listeners for Enter key on search input
    const searchInput = document.getElementById('searchConvoInput');
    if (searchInput) {
        searchInput.addEventListener('keypress', function(e) {
            if (e.key === 'Enter') {
                applyConvoFilters();
            }
        });
    }

    // Select All checkbox functionality
    const selectAllCheckbox = document.getElementById('selectAllUsers');
    // const userCheckboxes = document.getElementsByClassName('user-select'); // Declared dynamically now
    const deleteSelectedBtn = document.getElementById('deleteSelectedUsers');
    const editSelectedBtn = document.getElementById('editSelectedUsers'); 
    
    // Debug logging for user management buttons
    console.log('User Management Elements:', {
        selectAllCheckbox: selectAllCheckbox,
        deleteSelectedBtn: deleteSelectedBtn,
        editSelectedBtn: editSelectedBtn
    });

    // Function to update Edit and Delete button states
    function updateActionButtonsState() {
        const currentSelectedCheckboxes = document.getElementsByClassName('user-select'); 
        const checkedCount = Array.from(currentSelectedCheckboxes).filter(cb => cb.checked).length;
        
        console.log('Updating action button states. Checked count:', checkedCount);

        if (deleteSelectedBtn) {
            deleteSelectedBtn.disabled = (checkedCount === 0);
            console.log('Delete button disabled:', deleteSelectedBtn.disabled);
        }
        if (editSelectedBtn) {
            editSelectedBtn.disabled = (checkedCount !== 1);
            console.log('Edit button disabled:', editSelectedBtn.disabled);
            
            // Add visual feedback for the edit button
            if (checkedCount === 1) {
                editSelectedBtn.classList.remove('btn-secondary');
                editSelectedBtn.classList.add('btn-info');
                editSelectedBtn.textContent = 'Edit Selected';
            } else if (checkedCount === 0) {
                editSelectedBtn.classList.remove('btn-info');
                editSelectedBtn.classList.add('btn-secondary');
                editSelectedBtn.textContent = 'Edit Selected (Select 1 user)';
            } else {
                editSelectedBtn.classList.remove('btn-info');
                editSelectedBtn.classList.add('btn-secondary');
                editSelectedBtn.textContent = 'Edit Selected (Select only 1 user)';
            }
        }
    }

    if (selectAllCheckbox) {
        selectAllCheckbox.addEventListener('change', function() {
            const userCheckboxesInstance = document.getElementsByClassName('user-select'); // Get current instance
            Array.from(userCheckboxesInstance).forEach(checkbox => {
                checkbox.checked = this.checked;
            });
            updateActionButtonsState(); 
        });
    }

    // Individual checkbox functionality (Event Delegation)
    const userTableBody = document.getElementById('userTableBody');
    if (userTableBody) {
        userTableBody.addEventListener('change', function(e) {
            if (e.target.classList.contains('user-select')) {
                updateActionButtonsState(); 
                // Update select all checkbox
                const currentSelectedCheckboxes = document.getElementsByClassName('user-select'); 
                const allChecked = Array.from(currentSelectedCheckboxes).every(cb => cb.checked);
                if (selectAllCheckbox) {
                    selectAllCheckbox.checked = allChecked;
                }
            }
        });
    }

    // Delete selected users
    if (deleteSelectedBtn) {
        deleteSelectedBtn.addEventListener('click', function() {
            const userCheckboxesInstance = document.getElementsByClassName('user-select');
            const selectedIds = Array.from(userCheckboxesInstance)
                .filter(cb => cb.checked)
                .map(cb => cb.value);
            
            if (selectedIds.length > 0) {
                const deleteModal = new bootstrap.Modal(document.getElementById('deleteUsersModal'));
                deleteModal.show();
            }
        });
    }

    // Confirm delete users
    const confirmDeleteBtn = document.getElementById('confirmDeleteUsers');
    if (confirmDeleteBtn) {
        confirmDeleteBtn.addEventListener('click', function() {
            const userCheckboxesInstance = document.getElementsByClassName('user-select');
            const selectedIds = Array.from(userCheckboxesInstance)
                .filter(cb => cb.checked)
                .map(cb => cb.value);

            fetch(window.adminUrls.deleteSelectedUsers, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({ user_ids: selectedIds })
            })
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                     // Hide the modal
                    const deleteModal = bootstrap.Modal.getInstance(document.getElementById('deleteUsersModal'));
                    if (deleteModal) {
                        deleteModal.hide();
                    }
                    updateUserTable(); // Update table first
                    showSuccessMessage(data.message || 'Users deleted successfully'); // Then show message
                } else {
                    showErrorMessage('Error deleting users: ' + (data.error || 'Unknown error'));
                }
            })
            .catch(error => {
                console.error('Error:', error);
                showErrorMessage('Error deleting users: Network or server error');
            });
        });
    }

    // Add user functionality
    const submitAddUserBtn = document.getElementById('submitAddUser');
    if (submitAddUserBtn) {
        submitAddUserBtn.addEventListener('click', function() {
            const lastName = document.getElementById('lastName').value.trim();
            const email = document.getElementById('email').value.trim();
            const loRootIds = document.getElementById('loRootIds').value.trim();

            if (!lastName || !email) {
                // Show error message directly in the modal if possible, or use existing
                const addUserModalBody = document.getElementById('addUserModal').querySelector('.modal-body');
                let errorDiv = addUserModalBody.querySelector('.alert-danger');
                if (!errorDiv) {
                    errorDiv = document.createElement('div');
                    errorDiv.className = 'alert alert-danger mt-2';
                    addUserModalBody.insertBefore(errorDiv, addUserModalBody.firstChild);
                }
                errorDiv.textContent = 'Please fill in all required fields.';
                return;
            }

            fetch(window.adminUrls.addUser, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    last_name: lastName,
                    email: email,
                    lo_root_ids: loRootIds ? loRootIds.split(';').filter(id => id.trim()) : []
                })
            })
            .then(response => response.json())
            .then(data => {
                const addUserModal = bootstrap.Modal.getInstance(document.getElementById('addUserModal'));
                if (data.success) {
                    if (addUserModal) {
                        addUserModal.hide();
                    }
                    // Clear the form
                    document.getElementById('addUserForm').reset();
                     // Remove any modal-specific error messages
                    const addUserModalBody = document.getElementById('addUserModal').querySelector('.modal-body');
                    let errorDiv = addUserModalBody.querySelector('.alert-danger');
                    if (errorDiv) errorDiv.remove();

                    updateUserTable(); // Update table first
                    showSuccessMessage(data.message || 'User added successfully'); // Then show message
                } else {
                    // Show error message directly in the modal
                    const addUserModalBody = document.getElementById('addUserModal').querySelector('.modal-body');
                    let errorDiv = addUserModalBody.querySelector('.alert-danger');
                    if (!errorDiv) {
                        errorDiv = document.createElement('div');
                        errorDiv.className = 'alert alert-danger mt-2';
                        addUserModalBody.insertBefore(errorDiv, addUserModalBody.firstChild);
                    }
                    errorDiv.textContent = 'Error adding user: ' + (data.error || 'Unknown error');
                }
            })
            .catch(error => {
                console.error('Error:', error);
                const addUserModalBody = document.getElementById('addUserModal').querySelector('.modal-body');
                let errorDiv = addUserModalBody.querySelector('.alert-danger');
                if (!errorDiv) {
                    errorDiv = document.createElement('div');
                    errorDiv.className = 'alert alert-danger mt-2';
                    addUserModalBody.insertBefore(errorDiv, addUserModalBody.firstChild);
                }
                errorDiv.textContent = 'Error adding user: Network or server error.';
            });
        });
    }
    
    // Helper to remove existing alerts before showing a new one to avoid stacking
    function clearGlobalAlerts(){
        const usersMgmtSection = document.getElementById('users-mgmt');
        if(usersMgmtSection){
            const existingAlerts = usersMgmtSection.querySelectorAll('.alert-success, .alert-danger');
            existingAlerts.forEach(alert => alert.remove());
        }
    }

    function showSuccessMessage(message) {
        clearGlobalAlerts();
        const alertDiv = document.createElement('div');
        alertDiv.className = 'alert alert-success alert-dismissible fade show';
        alertDiv.innerHTML = `
            ${message}
            <button type="button" class="btn-close" data-bs-dismiss="alert" aria-label="Close"></button>
        `;
        
        const usersMgmtSection = document.getElementById('users-mgmt');
        if (usersMgmtSection) {
            usersMgmtSection.insertBefore(alertDiv, usersMgmtSection.firstChild);
            
            setTimeout(() => {
                bootstrap.Alert.getOrCreateInstance(alertDiv).close();
            }, 3000);
        }
    }

    function showErrorMessage(message) {
        clearGlobalAlerts();
        const alertDiv = document.createElement('div');
        alertDiv.className = 'alert alert-danger alert-dismissible fade show';
        alertDiv.innerHTML = `
            ${message}
            <button type="button" class="btn-close" data-bs-dismiss="alert" aria-label="Close"></button>
        `;
        
        const usersMgmtSection = document.getElementById('users-mgmt');
        if (usersMgmtSection) {
            usersMgmtSection.insertBefore(alertDiv, usersMgmtSection.firstChild);

            setTimeout(() => {
                 bootstrap.Alert.getOrCreateInstance(alertDiv).close();
            }, 5000);
        }
    }

    function updateUserTable() {
        fetch(window.adminUrls.getUsers)
            .then(response => response.json())
            .then(data => {
                const tbody = document.getElementById('userTableBody');
                if (tbody && data.users) {
                    tbody.innerHTML = data.users.map(user => `
                        <tr>
                            <td>
                                <input type="checkbox" class="form-check-input user-select" value="${user.id}">
                            </td>
                            <td>${user.id}</td>
                            <td>${user.last_name}</td>
                            <td>${user.email}</td>
                            <td>${user.visit_count}</td>
                            <td>${user.status}</td>
                            <td>${user.date_added}</td>
                            <td>${user.expiry_date}</td>
                            <td>${user.lo_root_ids.join(', ')}</td>
                        </tr>
                    `).join('');
                    // After updating table, re-apply filters and update button states
                    filterTable(); 
                    updateActionButtonsState();
                    if(selectAllCheckbox) selectAllCheckbox.checked = false; // Reset select all
                }
            });
    }

    // Column filtering
    const columnFilters = document.querySelectorAll('.column-filter');
    columnFilters.forEach(filter => {
        filter.addEventListener('input', filterTable);
        filter.addEventListener('change', filterTable); // for select/date inputs
    });

    function filterTable() {
        const tbody = document.getElementById('userTableBody');
        if (!tbody) return;
        
        const rows = tbody.getElementsByTagName('tr');
        const filters = {};
        
        // Collect all filter values
        columnFilters.forEach(filter => {
            const column = filter.dataset.column;
            const value = filter.value.trim().toLowerCase();
            if (value) filters[column] = value;
        });

        Array.from(rows).forEach(row => {
            let show = true;
            const cells = row.getElementsByTagName('td');
            
            // Skip rows that don't have enough cells (e.g. if table is empty or malformed)
            if (cells.length < 9) {
                 row.style.display = ''; // Show potentially malformed rows or empty state rows
                 return;
            }

            // ID filter (case-insensitive partial match)
             if (filters.id && cells[1]) {
                const idVal = cells[1].textContent.trim().toLowerCase();
                if (!idVal.includes(filters.id)) {
                    show = false;
                }
            }

            // Last Name filter (case-insensitive partial match)
            if (show && filters.last_name && cells[2]) {
                const lastName = cells[2].textContent.trim().toLowerCase();
                if (!lastName.includes(filters.last_name)) {
                    show = false;
                }
            }

            // Email filter (case-insensitive partial match)
            if (show && filters.email && cells[3]) {
                const email = cells[3].textContent.trim().toLowerCase();
                if (!email.includes(filters.email)) {
                    show = false;
                }
            }

            // Visit Count filter (exact match)
            if (show && filters.visit_count && cells[4]) {
                const visitCount = cells[4].textContent.trim();
                if (visitCount !== filters.visit_count) {
                    show = false;
                }
            }

            // Status filter (exact match, case-insensitive)
            if (show && filters.status && cells[5]) {
                const status = cells[5].textContent.trim().toLowerCase();
                if (status !== filters.status) {
                    show = false;
                }
            }

            // Date Added filter (YYYY-MM-DD match)
            if (show && filters.date_added && cells[6]) {
                const dateAdded = cells[6].textContent.trim().split('T')[0]; // Get YYYY-MM-DD part
                if (dateAdded !== filters.date_added) {
                    show = false;
                }
            }

            // Expiry Date filter (YYYY-MM-DD match)
            if (show && filters.expiry_date && cells[7]) {
                const expiryDate = cells[7].textContent.trim().split('T')[0]; // Get YYYY-MM-DD part
                if (expiryDate !== filters.expiry_date) {
                    show = false;
                }
            }

            // LO Root IDs filter (match any ID in the comma-separated list)
            if (show && filters.lo_root_ids && cells[8]) {
                const cellLoIds = cells[8].textContent.toLowerCase().split(',').map(id => id.trim());
                const filterLoId = filters.lo_root_ids.toLowerCase();
                if (!cellLoIds.some(id => id.includes(filterLoId))) {
                    show = false;
                }
            }

            // Show/hide the row
            row.style.display = show ? '' : 'none';
        });
        // After filtering, update button states based on visible and checked items
        updateActionButtonsState();
    }

    // Initialize filters on page load
    filterTable();
    
    // Initialize button states on page load
    updateActionButtonsState();
    
    // Log initialization completion
    console.log('Admin scripts initialization completed');

    // Edit User functionality
    const editUserModalElement = document.getElementById('editUserModal');
    let editModal = null;
    
    // Initialize Bootstrap modal with better error handling
    if (editUserModalElement) {
        try {
            editModal = new bootstrap.Modal(editUserModalElement, {
                backdrop: 'static',
                keyboard: false
            });
            console.log('Bootstrap Modal initialized successfully');
        } catch (error) {
            console.error('Error initializing Bootstrap Modal:', error);
            editModal = null;
        }
    } else {
        console.error('Edit User Modal element not found in DOM');
    }
    
    // Debug logging to identify issues
    console.log('Edit User Modal Element:', editUserModalElement);
    console.log('Edit Modal Instance:', editModal);
    console.log('Edit Selected Button:', editSelectedBtn);

    // Edit button click handler
    if (editSelectedBtn) {
        console.log('Adding event listener to Edit Selected button');
        editSelectedBtn.addEventListener('click', function() {
            console.log('Edit Selected button clicked');
            
            const selectedUsers = document.querySelectorAll('.user-select:checked');
            console.log('Selected user checkboxes:', selectedUsers);
            
            if (selectedUsers.length === 0) {
                alert('Please select exactly one user to edit');
                return;
            }
            
            if (selectedUsers.length > 1) {
                alert('Please select only one user to edit');
                return;
            }
            
            const selectedUser = selectedUsers[0];
            const row = selectedUser.closest('tr');
            const cells = row.getElementsByTagName('td');
            
            console.log('Row cells:', cells);
            console.log('Cells content:', Array.from(cells).map(cell => cell.textContent));

            // Check if modal elements exist before populating
            const editUserIdField = document.getElementById('editUserId');
            const editLastNameField = document.getElementById('editLastName');
            const editEmailField = document.getElementById('editEmail');
            const editStatusField = document.getElementById('editStatus');
            const editExpiryDateField = document.getElementById('editExpiryDate');
            const editLoRootIdsField = document.getElementById('editLoRootIds');
            
            console.log('Modal form fields:', {
                editUserId: editUserIdField,
                editLastName: editLastNameField,
                editEmail: editEmailField,
                editStatus: editStatusField,
                editExpiryDate: editExpiryDateField,
                editLoRootIds: editLoRootIdsField
            });

            if (!editUserIdField || !editLastNameField || !editEmailField || !editStatusField || !editExpiryDateField || !editLoRootIdsField) {
                console.error('Some modal form fields are missing');
                alert('Error: Modal form fields are not properly loaded. Please refresh the page and try again.');
                return;
            }

            // Populate the edit form
            editUserIdField.value = cells[1].textContent.trim();
            editLastNameField.value = cells[2].textContent.trim();
            editEmailField.value = cells[3].textContent.trim();
            editStatusField.value = cells[5].textContent.trim().toLowerCase();
            editExpiryDateField.value = formatDateForInput(cells[7].textContent.trim());
            editLoRootIdsField.value = cells[8].textContent.trim();
            
            console.log('Form populated with values:', {
                id: editUserIdField.value,
                lastName: editLastNameField.value,
                email: editEmailField.value,
                status: editStatusField.value,
                expiryDate: editExpiryDateField.value,
                loRootIds: editLoRootIdsField.value
            });

            // Show modal with multiple fallback approaches
            try {
                if (editModal) {
                    console.log('Showing edit modal using Bootstrap Modal instance');
                    
                    // Add CSS debugging
                    console.log('Modal element styles before show:', {
                        display: editUserModalElement.style.display,
                        visibility: editUserModalElement.style.visibility,
                        opacity: editUserModalElement.style.opacity,
                        zIndex: window.getComputedStyle(editUserModalElement).zIndex,
                        position: window.getComputedStyle(editUserModalElement).position
                    });
                    
                    // Force CSS styles to ensure visibility
                    editUserModalElement.style.display = 'block';
                    editUserModalElement.style.visibility = 'visible';
                    editUserModalElement.style.opacity = '1';
                    editUserModalElement.style.zIndex = '9999';
                    editUserModalElement.style.position = 'fixed';
                    editUserModalElement.style.top = '50%';
                    editUserModalElement.style.left = '50%';
                    editUserModalElement.style.transform = 'translate(-50%, -50%)';
                    
                    editModal.show();
                    
                    // Check if modal is actually shown after show() call
                    setTimeout(() => {
                        console.log('Modal element styles after show:', {
                            display: editUserModalElement.style.display,
                            visibility: editUserModalElement.style.visibility,
                            opacity: editUserModalElement.style.opacity,
                            hasShowClass: editUserModalElement.classList.contains('show'),
                            ariaHidden: editUserModalElement.getAttribute('aria-hidden'),
                            isVisible: editUserModalElement.offsetHeight > 0
                        });
                        
                        // If modal is still not visible, force it with aggressive CSS
                        if (!editUserModalElement.classList.contains('show') || editUserModalElement.offsetHeight === 0) {
                            console.log('Modal not properly shown, forcing visibility with aggressive CSS');
                            
                            // CREATE A COMPLETELY NEW MODAL FROM SCRATCH
                            console.log('Bootstrap modal failed completely. Creating new modal from scratch.');
                            
                            // Remove existing modal if any
                            const existingCustomModal = document.getElementById('customEditUserModal');
                            if (existingCustomModal) {
                                existingCustomModal.remove();
                            }
                            
                            // Create completely new modal HTML
                            const customModal = document.createElement('div');
                            customModal.id = 'customEditUserModal';
                            customModal.style.cssText = `
                                position: fixed !important;
                                top: 0 !important;
                                left: 0 !important;
                                width: 100vw !important;
                                height: 100vh !important;
                                background-color: rgba(0, 0, 0, 0.8) !important;
                                z-index: 999999 !important;
                                display: flex !important;
                                align-items: center !important;
                                justify-content: center !important;
                                font-family: 'Segoe UI', system-ui, sans-serif !important;
                            `;
                            
                            customModal.innerHTML = `
                                <div style="
                                    background: white !important;
                                    border-radius: 8px !important;
                                    box-shadow: 0 10px 30px rgba(0,0,0,0.3) !important;
                                    width: 90% !important;
                                    max-width: 500px !important;
                                    max-height: 90vh !important;
                                    overflow: auto !important;
                                    position: relative !important;
                                ">
                                    <div style="
                                        padding: 20px !important;
                                        border-bottom: 1px solid #dee2e6 !important;
                                        display: flex !important;
                                        justify-content: space-between !important;
                                        align-items: center !important;
                                    ">
                                        <h5 style="margin: 0 !important; font-size: 1.25rem !important; font-weight: 600 !important;">Edit User</h5>
                                        <button id="customCloseBtn" style="
                                            background: none !important;
                                            border: none !important;
                                            font-size: 24px !important;
                                            cursor: pointer !important;
                                            padding: 0 !important;
                                            width: 30px !important;
                                            height: 30px !important;
                                            display: flex !important;
                                            align-items: center !important;
                                            justify-content: center !important;
                                        ">×</button>
                                    </div>
                                    <div style="padding: 20px !important;">
                                        <div style="margin-bottom: 15px !important;">
                                            <label style="display: block !important; margin-bottom: 5px !important; font-weight: 500 !important;">Last Name</label>
                                            <input type="text" id="customLastName" value="${editLastNameField.value}" style="
                                                width: 100% !important;
                                                padding: 8px 12px !important;
                                                border: 1px solid #ced4da !important;
                                                border-radius: 4px !important;
                                                font-size: 14px !important;
                                            ">
                                        </div>
                                        <div style="margin-bottom: 15px !important;">
                                            <label style="display: block !important; margin-bottom: 5px !important; font-weight: 500 !important;">Email</label>
                                            <input type="email" id="customEmail" value="${editEmailField.value}" style="
                                                width: 100% !important;
                                                padding: 8px 12px !important;
                                                border: 1px solid #ced4da !important;
                                                border-radius: 4px !important;
                                                font-size: 14px !important;
                                            ">
                                        </div>
                                        <div style="margin-bottom: 15px !important;">
                                            <label style="display: block !important; margin-bottom: 5px !important; font-weight: 500 !important;">Status</label>
                                            <select id="customStatus" style="
                                                width: 100% !important;
                                                padding: 8px 12px !important;
                                                border: 1px solid #ced4da !important;
                                                border-radius: 4px !important;
                                                font-size: 14px !important;
                                            ">
                                                <option value="active" ${editStatusField.value === 'active' ? 'selected' : ''}>Active</option>
                                                <option value="inactive" ${editStatusField.value === 'inactive' ? 'selected' : ''}>Inactive</option>
                                            </select>
                                        </div>
                                        <div style="margin-bottom: 15px !important;">
                                            <label style="display: block !important; margin-bottom: 5px !important; font-weight: 500 !important;">Expiry Date</label>
                                            <input type="date" id="customExpiryDate" value="${editExpiryDateField.value}" style="
                                                width: 100% !important;
                                                padding: 8px 12px !important;
                                                border: 1px solid #ced4da !important;
                                                border-radius: 4px !important;
                                                font-size: 14px !important;
                                            ">
                                        </div>
                                        <div style="margin-bottom: 15px !important;">
                                            <label style="display: block !important; margin-bottom: 5px !important; font-weight: 500 !important;">LO Root IDs</label>
                                            <input type="text" id="customLoRootIds" value="${editLoRootIdsField.value}" placeholder="e.g. ID1;ID2;ID3" style="
                                                width: 100% !important;
                                                padding: 8px 12px !important;
                                                border: 1px solid #ced4da !important;
                                                border-radius: 4px !important;
                                                font-size: 14px !important;
                                            ">
                                            <small style="color: #6c757d !important; font-size: 12px !important;">Separate multiple IDs with semicolons (;)</small>
                                        </div>
                                    </div>
                                    <div style="
                                        padding: 15px 20px !important;
                                        border-top: 1px solid #dee2e6 !important;
                                        display: flex !important;
                                        justify-content: flex-end !important;
                                        gap: 10px !important;
                                    ">
                                        <button id="customCancelBtn" style="
                                            padding: 8px 16px !important;
                                            background: #6c757d !important;
                                            color: white !important;
                                            border: none !important;
                                            border-radius: 4px !important;
                                            cursor: pointer !important;
                                            font-size: 14px !important;
                                        ">Cancel</button>
                                        <button id="customSaveBtn" style="
                                            padding: 8px 16px !important;
                                            background: #007bff !important;
                                            color: white !important;
                                            border: none !important;
                                            border-radius: 4px !important;
                                            cursor: pointer !important;
                                            font-size: 14px !important;
                                        ">Save Changes</button>
                                    </div>
                                </div>
                            `;
                            
                            // Add to body
                            document.body.appendChild(customModal);
                            document.body.style.overflow = 'hidden';
                            
                            console.log('Custom modal created and added to body');
                            
                            // Add event listeners
                            const closeModal = () => {
                                console.log('Closing custom modal');
                                
                                // Remove the modal completely
                                if (customModal && customModal.parentNode) {
                                    customModal.parentNode.removeChild(customModal);
                                }
                                
                                // Restore body styles
                                document.body.style.overflow = '';
                                document.body.style.paddingRight = '';
                                document.body.classList.remove('modal-open');
                                
                                // Remove any modal backdrops that might exist
                                const existingBackdrops = document.querySelectorAll('.modal-backdrop');
                                existingBackdrops.forEach(backdrop => {
                                    if (backdrop.parentNode) {
                                        backdrop.parentNode.removeChild(backdrop);
                                    }
                                });
                                
                                // Remove any other custom modals that might exist
                                const existingCustomModals = document.querySelectorAll('#customEditUserModal');
                                existingCustomModals.forEach(modal => {
                                    if (modal.parentNode) {
                                        modal.parentNode.removeChild(modal);
                                    }
                                });
                                
                                // Also clean up any Bootstrap modals that might be open
                                const bootstrapModals = document.querySelectorAll('.modal.show');
                                bootstrapModals.forEach(modal => {
                                    modal.classList.remove('show');
                                    modal.style.display = 'none';
                                    modal.setAttribute('aria-hidden', 'true');
                                    modal.removeAttribute('aria-modal');
                                });
                                
                                // Remove any modal-open class from body
                                document.body.classList.remove('modal-open');
                                
                                // Clean up any additional styles that might be interfering
                                document.documentElement.style.overflow = '';
                                
                                console.log('Custom modal closed and cleanup completed');
                            };
                            
                            document.getElementById('customCloseBtn').addEventListener('click', closeModal);
                            document.getElementById('customCancelBtn').addEventListener('click', closeModal);
                            
                            // Click outside to close
                            customModal.addEventListener('click', function(e) {
                                if (e.target === this) {
                                    closeModal();
                                }
                            });
                            
                            // ESC to close
                            document.addEventListener('keydown', function(e) {
                                if (e.key === 'Escape') {
                                    closeModal();
                                }
                            }, { once: true });
                            
                            // Save button functionality
                            document.getElementById('customSaveBtn').addEventListener('click', function() {
                                console.log('Custom modal save button clicked');
                                
                                const formData = new FormData();
                                formData.append('user_id', editUserIdField.value);
                                formData.append('last_name', document.getElementById('customLastName').value);
                                formData.append('email', document.getElementById('customEmail').value);
                                formData.append('status', document.getElementById('customStatus').value);
                                formData.append('expiry_date', document.getElementById('customExpiryDate').value);
                                formData.append('lo_root_ids', document.getElementById('customLoRootIds').value);
                                
                                this.disabled = true;
                                this.innerHTML = 'Saving...';
                                
                                fetch(window.adminUrls.editUser, {
                                    method: 'POST',
                                    body: formData
                                })
                                .then(response => response.json())
                                .then(data => {
                                    if (data.success) {
                                        console.log('User update successful, closing modal');
                                        closeModal();
                                        updateUserTable();
                                        showSuccessMessage(data.message || 'User updated successfully');
                                    } else {
                                        alert('Error: ' + (data.error || 'Could not update user.'));
                                        this.disabled = false;
                                        this.innerHTML = 'Save Changes';
                                    }
                                })
                                .catch(error => {
                                    console.error('Network error:', error);
                                    alert('Network error: ' + error.message);
                                    this.disabled = false;
                                    this.innerHTML = 'Save Changes';
                                });
                            });
                        }
                    }, 100);
                } else {
                    console.log('Bootstrap Modal instance not available, trying jQuery approach');
                    // Try jQuery approach if available
                    if (typeof $ !== 'undefined') {
                        $(editUserModalElement).modal('show');
                    } else {
                        console.log('jQuery not available, using manual modal display');
                        // Manual modal display
                        editUserModalElement.style.display = 'block';
                        editUserModalElement.classList.add('show');
                        editUserModalElement.setAttribute('aria-hidden', 'false');
                        editUserModalElement.setAttribute('aria-modal', 'true');
                        editUserModalElement.style.paddingRight = '17px';
                        document.body.classList.add('modal-open');
                        document.body.style.paddingRight = '17px';
                        
                        // Create and add backdrop
                        let backdrop = document.querySelector('.modal-backdrop');
                        if (!backdrop) {
                            backdrop = document.createElement('div');
                            backdrop.className = 'modal-backdrop fade show';
                            document.body.appendChild(backdrop);
                        }
                        
                        // Add close functionality
                        const closeButtons = editUserModalElement.querySelectorAll('[data-bs-dismiss="modal"], .btn-close');
                        closeButtons.forEach(button => {
                            button.addEventListener('click', function() {
                                editUserModalElement.style.display = 'none';
                                editUserModalElement.classList.remove('show');
                                editUserModalElement.setAttribute('aria-hidden', 'true');
                                editUserModalElement.removeAttribute('aria-modal');
                                editUserModalElement.style.paddingRight = '';
                                document.body.classList.remove('modal-open');
                                document.body.style.paddingRight = '';
                                if (backdrop) backdrop.remove();
                            });
                        });
                    }
                }
            } catch (error) {
                console.error('Error showing modal:', error);
                
                // Emergency fallback - force show modal with inline styles
                console.log('Using emergency fallback to show modal');
                editUserModalElement.style.cssText = `
                    display: block !important;
                    position: fixed !important;
                    top: 50% !important;
                    left: 50% !important;
                    transform: translate(-50%, -50%) !important;
                    z-index: 9999 !important;
                    background: rgba(0,0,0,0.5) !important;
                    width: 100vw !important;
                    height: 100vh !important;
                `;
                editUserModalElement.classList.add('show');
                editUserModalElement.setAttribute('aria-hidden', 'false');
                
                alert('Modal opened using emergency fallback. If you can see this alert but not the modal, there may be a CSS conflict.');
            }
        });
    } else {
        console.error('Edit Selected button not found');
    }

    // Format date for input field
    function formatDateForInput(dateStr) {
        if (!dateStr || dateStr.toLowerCase() === 'n/a' || dateStr.toLowerCase() === 'none') return '';
        try {
            const date = new Date(dateStr);
            if (isNaN(date.getTime())) return ''; // Invalid date
            return date.toISOString().split('T')[0];
        } catch (e) {
            return ''; // Error parsing date
        }
    }

    // Handle edit form submission
    const submitEditUserBtn = document.getElementById('submitEditUser');
    if (submitEditUserBtn) {
        submitEditUserBtn.addEventListener('click', function() {
            console.log('Submit Edit User button clicked');
            
            const formData = new FormData();
            formData.append('user_id', document.getElementById('editUserId').value);
            formData.append('last_name', document.getElementById('editLastName').value);
            formData.append('email', document.getElementById('editEmail').value);
            formData.append('status', document.getElementById('editStatus').value);
            formData.append('expiry_date', document.getElementById('editExpiryDate').value);
            formData.append('lo_root_ids', document.getElementById('editLoRootIds').value);
            
            console.log('Submitting form data:', {
                user_id: formData.get('user_id'),
                last_name: formData.get('last_name'),
                email: formData.get('email'),
                status: formData.get('status'),
                expiry_date: formData.get('expiry_date'),
                lo_root_ids: formData.get('lo_root_ids')
            });

            // Disable button and show loading state
            this.disabled = true;
            this.innerHTML = '<span class="spinner-border spinner-border-sm" role="status"></span> Saving...';

            fetch(window.adminUrls.editUser, {
                method: 'POST',
                body: formData 
            })
            .then(response => {
                console.log('Server response status:', response.status);
                return response.json();
            })
            .then(data => {
                console.log('Server response data:', data);
                
                if (data.success) {
                    // Close modal aggressively
                    const editUserModalElement = document.getElementById('editUserModal');
                    editUserModalElement.style.display = 'none';
                    editUserModalElement.classList.remove('show');
                    editUserModalElement.setAttribute('aria-hidden', 'true');
                    editUserModalElement.removeAttribute('aria-modal');
                    document.body.classList.remove('modal-open');
                    document.body.style.overflow = '';
                    document.body.style.paddingRight = '';
                    
                    updateUserTable(); // Refresh table content
                    showSuccessMessage(data.message || 'User updated successfully');
                } else {
                    // Show error in modal
                    const editUserModalBody = editUserModalElement.querySelector('.modal-body');
                    let errorDiv = editUserModalBody.querySelector('.alert-danger');
                    if(!errorDiv){
                        errorDiv = document.createElement('div');
                        errorDiv.className = 'alert alert-danger mt-2';
                        editUserModalBody.insertBefore(errorDiv, editUserModalBody.firstChild);
                    }
                    errorDiv.textContent = 'Error: ' + (data.error || 'Could not update user.');
                }
                
                // Reset button state
                this.disabled = false;
                this.innerHTML = 'Save Changes';
            })
            .catch(error => {
                console.error('Network error:', error);
                
                const editUserModalElement = document.getElementById('editUserModal');
                const editUserModalBody = editUserModalElement.querySelector('.modal-body');
                let errorDiv = editUserModalBody.querySelector('.alert-danger');
                if(!errorDiv){
                   errorDiv = document.createElement('div');
                   errorDiv.className = 'alert alert-danger mt-2';
                   editUserModalBody.insertBefore(errorDiv, editUserModalBody.firstChild);
                }
                errorDiv.textContent = 'Network error: ' + error.message;
                
                // Reset button state
                this.disabled = false;
                this.innerHTML = 'Save Changes';
            });
        });
    } else {
        console.error('Submit Edit User button not found');
    }

    // Initialize new chatbot management features
    initializeChatbotManagement();
    enhanceChatbotCardInteractions();

    // 👈 NEW: Setup event listeners for auto-delete setting updates
    document.querySelectorAll('.update-auto-delete-btn').forEach(button => {
        button.addEventListener('click', function() {
            const form = this.closest('.update-auto-delete-form');
            const chatbotCode = form.querySelector('.chatbot-name').value;
            const autoDeleteDays = form.querySelector('.auto-delete-field').value;
            
            // Show a brief loading indicator on the button
            const originalText = this.innerHTML;
            this.innerHTML = '<i class="bi bi-hourglass-split"></i> Updating...';
            this.disabled = true;
            
            // Create form data for POST request
            const formData = new FormData();
            formData.append('chatbot_code', chatbotCode);
            formData.append('auto_delete_days', autoDeleteDays);
            
            fetch('/admin/update_auto_delete_days', {
                method: 'POST',
                body: formData
            })
            .then(response => response.json())
            .then(data => {
                // Reset button state
                this.innerHTML = originalText;
                this.disabled = false;
                
                if (data.success) {
                    // Show temporary success message next to the button
                    const successMsg = document.createElement('span');
                    successMsg.className = 'text-success ms-2';
                    successMsg.innerHTML = '<i class="bi bi-check-circle"></i> Updated!';
                    this.parentNode.appendChild(successMsg);
                    
                    // Update the current setting text
                    const settingText = form.querySelector('.form-text small');
                    if (settingText && data.auto_delete_text) {
                        settingText.textContent = `Current setting: ${data.auto_delete_text}`;
                    }
                    
                    // Remove success message after 2.5 seconds
                    setTimeout(() => {
                        successMsg.remove();
                    }, 2500);
                    
                    // Log the update
                    if (autoDeleteDays) {
                        console.log(`Auto-delete setting updated for ${chatbotCode}: ${autoDeleteDays} days`);
                    } else {
                        console.log(`Auto-delete disabled for ${chatbotCode}: conversations will be kept indefinitely`);
                    }
                } else {
                    alert('Error updating auto-delete setting: ' + data.error);
                }
            })
            .catch(error => {
                // Reset button state
                this.innerHTML = originalText;
                this.disabled = false;
                alert('Network error occurred. Please try again.');
                console.error('Error updating auto-delete settings:', error);
            });
        });
    });

}); // End of first DOMContentLoaded

// New Modern Chatbot Management Functions
function initializeChatbotManagement() {
    // Search functionality
    const searchInput = document.getElementById('chatbotSearchInput');
    if (searchInput) {
        searchInput.addEventListener('input', function() {
            filterChatbots(this.value.toLowerCase());
        });
    }

    // View toggle functionality
    const gridViewBtn = document.getElementById('gridViewBtn');
    const listViewBtn = document.getElementById('listViewBtn');
    const chatbotList = document.querySelector('.chatbot-list');

    if (gridViewBtn && listViewBtn && chatbotList) {
        gridViewBtn.addEventListener('click', function() {
            chatbotList.classList.remove('list-view');
            gridViewBtn.classList.add('active');
            listViewBtn.classList.remove('active');
            localStorage.setItem('chatbotViewMode', 'grid');
        });

        listViewBtn.addEventListener('click', function() {
            chatbotList.classList.add('list-view');
            listViewBtn.classList.add('active');
            gridViewBtn.classList.remove('active');
            localStorage.setItem('chatbotViewMode', 'list');
        });

        // Restore saved view mode
        const savedViewMode = localStorage.getItem('chatbotViewMode');
        if (savedViewMode === 'list') {
            listViewBtn.click();
        }
    }

    // Initialize intro message preview updates
    initializeIntroMessagePreviews();
    
    // Initialize collapsible sections
    initializeCollapsibleSections();
}

function filterChatbots(searchTerm) {
    const chatbotCards = document.querySelectorAll('.chatbot-card');
    let visibleCount = 0;

    chatbotCards.forEach(card => {
        const name = card.getAttribute('data-chatbot-name') || '';
        const id = card.getAttribute('data-chatbot-id') || '';
        const category = card.getAttribute('data-chatbot-category') || '';
        
        const matches = name.includes(searchTerm) || 
                      id.includes(searchTerm) || 
                      category.includes(searchTerm);

        if (matches) {
            card.style.display = '';
            visibleCount++;
        } else {
            card.style.display = 'none';
        }
    });

    // Update the count
    const countElement = document.getElementById('totalChatbotCount');
    if (countElement) {
        const totalCount = chatbotCards.length;
        if (searchTerm) {
            countElement.textContent = `${visibleCount} of ${totalCount}`;
        } else {
            countElement.textContent = totalCount;
        }
    }

    // Show/hide no results message
    showNoResultsMessage(visibleCount === 0 && searchTerm);
}

function showNoResultsMessage(show) {
    let noResultsElement = document.querySelector('.chatbot-no-search-results');
    
    if (show && !noResultsElement) {
        noResultsElement = document.createElement('div');
        noResultsElement.className = 'chatbot-no-results chatbot-no-search-results';
        noResultsElement.innerHTML = '<i class="bi bi-search"></i> No chatbots match your search criteria.';
        document.querySelector('.chatbot-list').appendChild(noResultsElement);
    } else if (!show && noResultsElement) {
        noResultsElement.remove();
    }
}

function initializeIntroMessagePreviews() {
    // Update intro message previews when quota or intro text changes
    document.querySelectorAll('.update-intro-form').forEach(form => {
        const introField = form.querySelector('.intro-field');
        const quotaField = form.closest('.card-body').querySelector('.quota-field');
        const previewElement = form.querySelector('.preview-text');
        const chatbotName = form.querySelector('.chatbot-name').value;
        const displayName = form.closest('.chatbot-card').querySelector('.chatbot-card-header h5').textContent;

        function updatePreview() {
            if (introField && previewElement) {
                let message = introField.value;
                const quota = quotaField ? quotaField.value : '3';
                
                message = message.replace(/{program}/g, displayName);
                message = message.replace(/{quota}/g, quota);
                
                previewElement.textContent = message;
            }
        }

        if (introField) {
            introField.addEventListener('input', updatePreview);
        }
        if (quotaField) {
            quotaField.addEventListener('input', updatePreview);
        }
    });
}

function initializeCollapsibleSections() {
    // Add smooth animations to collapsible sections
    document.querySelectorAll('.collapse').forEach(collapse => {
        collapse.addEventListener('show.bs.collapse', function() {
            const toggle = document.querySelector(`[data-bs-target="#${this.id}"]`);
            if (toggle) {
                toggle.classList.remove('collapsed');
            }
        });

        collapse.addEventListener('hide.bs.collapse', function() {
            const toggle = document.querySelector(`[data-bs-target="#${this.id}"]`);
            if (toggle) {
                toggle.classList.add('collapsed');
            }
        });
    });
}

function enhanceChatbotCardInteractions() {
    // Add keyboard shortcuts for chatbot management
    document.addEventListener('keydown', function(e) {
        // Ctrl/Cmd + F to focus search
        if ((e.ctrlKey || e.metaKey) && e.key === 'f') {
            const searchInput = document.getElementById('chatbotSearchInput');
            if (searchInput && document.querySelector('.tab-pane.active#manage-content')) {
                e.preventDefault();
                searchInput.focus();
                searchInput.select();
            }
        }
    });

    // Enhanced hover effects for cards
    document.querySelectorAll('.chatbot-card').forEach(card => {
        card.addEventListener('mouseenter', function() {
            this.style.transform = 'translateY(-4px)';
        });

        card.addEventListener('mouseleave', function() {
            this.style.transform = 'translateY(-2px)';
        });
    });
}

// ===== CSV Upload Enhancement Functions =====

function initializeCSVUploadEnhancements() {
    const csvUploadForm = document.getElementById('csvUploadForm');
    if (csvUploadForm) {
        csvUploadForm.addEventListener('submit', function(e) {
            const fileInput = document.getElementById('csvFileInput');
            if (!fileInput.files.length) {
                e.preventDefault();
                alert('Please select a CSV file to upload.');
                return;
            }
            
            const submitBtn = csvUploadForm.querySelector('button[type="submit"]');
            const originalHTML = submitBtn.innerHTML;
            
            // Update button to show processing state
            submitBtn.innerHTML = '<i class="bi bi-arrow-clockwise spinning"></i> Uploading & Syncing...';
            submitBtn.disabled = true;
            
            // Show processing message
            showCSVProcessingMessage('📤 Uploading CSV and synchronizing user access permissions...');
            
            // Store original button state for potential restoration
            csvUploadForm.dataset.originalButtonHTML = originalHTML;
        });
    }
}

function showCSVProcessingMessage(message) {
    // Remove any existing processing messages
    const existingMessage = document.querySelector('.csv-processing-alert');
    if (existingMessage) {
        existingMessage.remove();
    }
    
    // Create new processing message
    const alertDiv = document.createElement('div');
    alertDiv.className = 'alert alert-info mt-3 csv-processing-alert';
    alertDiv.innerHTML = `
        <div class="d-flex align-items-center">
            <div class="spinner-border spinner-border-sm text-info me-3" role="status">
                <span class="visually-hidden">Loading...</span>
            </div>
            <div>
                <strong>Processing...</strong><br>
                <small>${message}</small>
            </div>
        </div>
    `;
    
    const form = document.getElementById('csvUploadForm');
    if (form) {
        form.appendChild(alertDiv);
        
        // Auto-remove after 10 seconds (in case the page doesn't reload)
        setTimeout(() => {
            if (alertDiv.parentNode) {
                alertDiv.remove();
            }
        }, 10000);
    }
}

function enhanceCSVStatusDisplay() {
    // Add animation to CSV status refresh
    const refreshButton = document.querySelector('button[onclick="refreshCsvStatus()"]');
    if (refreshButton) {
        refreshButton.addEventListener('click', function() {
            this.querySelector('i').classList.add('spinning');
            
            setTimeout(() => {
                this.querySelector('i').classList.remove('spinning');
            }, 2000);
        });
    }
}

function showCSVUploadResult(success, message, details = null) {
    // Enhanced result display function for CSV uploads
    const alertType = success ? 'success' : 'danger';
    const iconClass = success ? 'bi-check-circle-fill' : 'bi-exclamation-circle-fill';
    
    let alertHTML = `
        <div class="alert alert-${alertType} mt-3">
            <div class="d-flex align-items-start">
                <i class="${iconClass} me-2 mt-1"></i>
                <div class="flex-grow-1">
                    <strong>${message}</strong>
                    ${details ? `<div class="mt-2 small">${details}</div>` : ''}
                </div>
            </div>
        </div>
    `;
    
    // Find appropriate container and add the result
    const container = document.querySelector('#csvManagement .card-body');
    if (container) {
        const tempDiv = document.createElement('div');
        tempDiv.innerHTML = alertHTML;
        container.appendChild(tempDiv.firstElementChild);
    }
}

// Initialize CSV enhancements when DOM is ready
document.addEventListener('DOMContentLoaded', function() {
    initializeCSVUploadEnhancements();
    enhanceCSVStatusDisplay();
});

// CSS Animation for spinning effect (if not already added)
if (!document.querySelector('#admin-spinner-styles')) {
    const style = document.createElement('style');
    style.id = 'admin-spinner-styles';
    style.textContent = `
        @keyframes spin {
            0% { transform: rotate(0deg); }
            100% { transform: rotate(360deg); }
        }
        .spinning {
            animation: spin 1s linear infinite;
        }
        .csv-processing-alert {
            border-left: 4px solid #0dcaf0;
            background-color: #e7f3ff;
        }
    `;
    document.head.appendChild(style);
}

// =============================================
// Duplicate Management Functions
// =============================================

function initializeDuplicateManagement() {
    const checkBtn = document.getElementById('checkDuplicatesBtn');
    const removeBtn = document.getElementById('removeDuplicatesBtn');
    
    if (checkBtn) {
        checkBtn.addEventListener('click', checkForDuplicates);
    }
    
    if (removeBtn) {
        removeBtn.addEventListener('click', removeDuplicates);
    }
}

function checkForDuplicates() {
    const checkBtn = document.getElementById('checkDuplicatesBtn');
    const statusDiv = document.getElementById('duplicateStatus');
    const lastCheckDiv = document.getElementById('lastDuplicateCheck');
    const removeBtn = document.getElementById('removeDuplicatesBtn');
    
    // Show loading state
    checkBtn.disabled = true;
    checkBtn.innerHTML = '<i class="bi bi-hourglass-split spinning"></i> Checking...';
    statusDiv.innerHTML = '<span class="text-info"><i class="bi bi-arrow-clockwise spinning"></i> Scanning database for duplicates...</span>';
    
    fetch('/admin/check_duplicates')
        .then(response => response.json())
        .then(data => {
            if (data.error) {
                throw new Error(data.error);
            }
            
            // Update status display
            const duplicatesFound = data.duplicates > 0;
            const statusClass = duplicatesFound ? 'text-warning' : 'text-success';
            const statusIcon = duplicatesFound ? 'bi-exclamation-triangle' : 'bi-check-circle';
            
            statusDiv.innerHTML = `
                <div class="${statusClass}">
                    <i class="bi ${statusIcon}"></i>
                    <strong>Total Records:</strong> ${data.total_records.toLocaleString()}<br>
                    <strong>Unique Emails:</strong> ${data.unique_emails.toLocaleString()}<br>
                    <strong>Duplicates Found:</strong> ${data.duplicates.toLocaleString()}
                    ${duplicatesFound ? ' ⚠️' : ' ✅'}
                </div>
            `;
            
            // Update last check time
            lastCheckDiv.innerHTML = `<span class="text-muted">${new Date().toLocaleString()}</span>`;
            
            // Enable/disable remove button
            removeBtn.disabled = !duplicatesFound;
            if (duplicatesFound) {
                removeBtn.classList.remove('btn-warning');
                removeBtn.classList.add('btn-danger');
            }
            
            // Show duplicate details if any found
            if (duplicatesFound && data.duplicate_details && data.duplicate_details.length > 0) {
                showDuplicateDetails(data.duplicate_details);
            } else {
                hideDuplicateDetails();
            }
            
            // Show success message
            showDuplicateMessage(
                duplicatesFound ? 'warning' : 'success',
                duplicatesFound 
                    ? `Found ${data.duplicates} duplicate records that can be cleaned up.`
                    : 'No duplicates found! Database is clean. 🎉'
            );
            
        })
        .catch(error => {
            console.error('Error checking duplicates:', error);
            statusDiv.innerHTML = `<span class="text-danger"><i class="bi bi-exclamation-triangle"></i> Error: ${error.message}</span>`;
            showDuplicateMessage('danger', `Error checking duplicates: ${error.message}`);
        })
        .finally(() => {
            // Reset button state
            checkBtn.disabled = false;
            checkBtn.innerHTML = '<i class="bi bi-search"></i> Check for Duplicates';
        });
}

function removeDuplicates() {
    const removeBtn = document.getElementById('removeDuplicatesBtn');
    const statusDiv = document.getElementById('duplicateStatus');
    
    // Confirm action
    if (!confirm('Are you sure you want to remove duplicate records? This action cannot be undone.\n\nDuplicates will be removed safely (keeping the oldest record for each email).')) {
        return;
    }
    
    // Show loading state
    removeBtn.disabled = true;
    removeBtn.innerHTML = '<i class="bi bi-hourglass-split spinning"></i> Removing...';
    statusDiv.innerHTML = '<span class="text-info"><i class="bi bi-arrow-clockwise spinning"></i> Removing duplicate records...</span>';
    
    fetch('/admin/remove_duplicates', {
        method: 'POST'
    })
        .then(response => response.json())
        .then(data => {
            if (!data.success) {
                throw new Error(data.error || 'Unknown error occurred');
            }
            
            // Update status display
            statusDiv.innerHTML = `
                <div class="text-success">
                    <i class="bi bi-check-circle"></i>
                    <strong>Cleanup Complete!</strong><br>
                    <strong>Records Removed:</strong> ${data.removed.toLocaleString()}<br>
                    <strong>Final Count:</strong> ${data.final_count.toLocaleString()}<br>
                    <strong>Remaining Duplicates:</strong> ${data.remaining_duplicates}
                </div>
            `;
            
            // Hide duplicate details
            hideDuplicateDetails();
            
            // Show success message
            showDuplicateMessage('success', data.message);
            
            // Update last check time
            const lastCheckDiv = document.getElementById('lastDuplicateCheck');
            lastCheckDiv.innerHTML = `<span class="text-muted">${new Date().toLocaleString()}</span>`;
            
        })
        .catch(error => {
            console.error('Error removing duplicates:', error);
            statusDiv.innerHTML = `<span class="text-danger"><i class="bi bi-exclamation-triangle"></i> Error: ${error.message}</span>`;
            showDuplicateMessage('danger', `Error removing duplicates: ${error.message}`);
        })
        .finally(() => {
            // Reset button state
            removeBtn.disabled = true;
            removeBtn.classList.remove('btn-danger');
            removeBtn.classList.add('btn-warning');
            removeBtn.innerHTML = '<i class="bi bi-trash"></i> Remove Duplicates';
        });
}

function showDuplicateDetails(duplicateDetails) {
    const detailsDiv = document.getElementById('duplicateDetails');
    const tableBody = document.getElementById('duplicateTableBody');
    
    // Clear existing content
    tableBody.innerHTML = '';
    
    // Add duplicate details to table
    duplicateDetails.forEach(detail => {
        const row = document.createElement('tr');
        row.innerHTML = `
            <td>${detail.email}</td>
            <td><span class="badge bg-warning">${detail.count}</span></td>
        `;
        tableBody.appendChild(row);
    });
    
    // Show details section
    detailsDiv.style.display = 'block';
}

function hideDuplicateDetails() {
    const detailsDiv = document.getElementById('duplicateDetails');
    detailsDiv.style.display = 'none';
}

function showDuplicateMessage(type, message) {
    const alertDiv = document.createElement('div');
    alertDiv.className = `alert alert-${type} alert-dismissible fade show mt-3`;
    alertDiv.innerHTML = `
        <strong>${type === 'success' ? 'Success!' : type === 'warning' ? 'Notice!' : 'Error!'}</strong> ${message}
        <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
    `;
    
    // Insert the alert after the duplicate management section
    const duplicateCard = document.querySelector('#duplicateManagement .card-body');
    if (duplicateCard) {
        // Remove any existing duplicate messages
        const existingAlerts = duplicateCard.querySelectorAll('.alert');
        existingAlerts.forEach(alert => {
            if (alert.textContent.includes('duplicate') || alert.textContent.includes('Success!') || alert.textContent.includes('Error!')) {
                alert.remove();
            }
        });
        
        duplicateCard.insertBefore(alertDiv, duplicateCard.firstChild);
    }
    
    // Auto-hide after 5 seconds
    setTimeout(() => {
        if (alertDiv.parentNode) {
            alertDiv.remove();
        }
    }, 8000);
}

// Initialize duplicate management when DOM is loaded
document.addEventListener('DOMContentLoaded', function() {
    initializeDuplicateManagement();
});
