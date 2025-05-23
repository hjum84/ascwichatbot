# Managing Existing Chatbots

This guide provides detailed information on managing existing chatbots in the administration interface, including editing content, modifying configurations, tracking usage statistics, and handling deletion/restoration operations.

## Table of Contents

1. [Admin Dashboard Overview](#admin-dashboard-overview)
2. [Viewing Existing Chatbots](#viewing-existing-chatbots)
3. [Editing Chatbot Content](#editing-chatbot-content)
4. [Managing Chatbot Settings](#managing-chatbot-settings)
5. [Monitoring Chatbot Usage](#monitoring-chatbot-usage)
6. [Deleting and Restoring Chatbots](#deleting-and-restoring-chatbots)
7. [Database Statistics](#database-statistics)

## Admin Dashboard Overview

The Admin Dashboard is accessible to authenticated administrators and provides comprehensive tools for managing chatbots. The interface has several tabs:

1. **Manage Existing Chatbots** - View and edit active chatbots
2. **Create New Chatbot** - Create and configure new chatbots
3. **Deleted Chatbots** - Manage previously deleted chatbots
4. **Database Statistics** - Monitor system usage and performance

## Viewing Existing Chatbots

The "Manage Existing Chatbots" tab displays all active chatbots in a card-based interface. Each card shows:

- **Chatbot Display Name** - The user-friendly name shown to users
- **Chatbot ID** - Unique identifier code for the chatbot (usually uppercase)
- **Description** - Brief overview of the chatbot's purpose
- **Daily Question Quota** - Maximum questions per user per day
- **Category** - Program classification (Standard, TAP, JSA, eLearning)
- **Intro Message** - Customizable greeting shown to users

The interface provides quick access buttons for:
- Editing content
- Modifying settings
- Deleting the chatbot

## Editing Chatbot Content

To edit a chatbot's knowledge base:

1. Click the **Edit Content** button on the chatbot card
2. The Edit Content modal appears with the following options:

### Direct Editing

- View and edit the entire content in a text editor
- Set character limits (50,000 - 100,000 characters)
- Enable/disable auto-summarization
- Save changes directly

### Adding New Content

1. Go to the "Upload New Files" tab in the edit modal
2. Select files to upload (supported formats: .txt, .pdf, .docx, .pptx)
3. Choose to either:
   - **Append** - Add new content to existing knowledge base
   - **Replace** - Completely replace current content
4. Preview combined content before saving
5. Apply auto-summarization if needed
6. Save changes

### Character Limit Considerations

- Default limit: 50,000 characters
- Higher limits increase token usage and API costs
- Enable auto-summarization to reduce content automatically
- The system shows warnings when content exceeds limits
- Character count indicators show current usage vs. limit

## Managing Chatbot Settings

Each chatbot has several configurable settings that can be modified:

### Updating Description

1. Edit the description text in the chatbot card
2. Click "Update Description" to save changes
3. The description appears on the chatbot selection screen for users

### Setting Daily Question Quota

1. Adjust the number input for "Daily Question Quota"
2. Click "Update" to save changes
3. This controls how many questions each user can ask per day
4. Default quota is 3 questions

### Changing Program Category

1. Select a category from the dropdown menu:
   - Standard Programs
   - TAP Programs
   - JSA Programs
   - eLearning
2. Click "Update" to save changes
3. Categories help organize chatbots in the user interface

### Customizing Intro Message

1. Edit the text in the "Chatbot Intro Message" field
2. Use placeholders:
   - `{program}` - Automatically replaced with the chatbot name
   - `{quota}` - Automatically replaced with the daily question quota
3. Preview shows how the message will appear to users
4. Click "Update Intro Message" to save changes

## Monitoring Chatbot Usage

The Admin Dashboard provides detailed usage statistics for each chatbot:

### Conversation Logs

1. Navigate to the "Data Management" tab
2. Go to the "Conversation Logs" section
3. Filter conversations by:
   - Chatbot
   - User
   - Search term in messages
4. View user questions and bot responses
5. Analyze conversation patterns and common questions

### Usage Statistics

The "Database Statistics" tab shows:

- Total messages per chatbot
- Unique users per chatbot
- Conversation counts
- Most active chatbots
- Content size statistics

### Top Chatbots Analysis

The dashboard displays the most active chatbots with:
- Total message count
- Unique conversation count
- Usage trends

## Deleting and Restoring Chatbots

### Deleting a Chatbot

1. Click the "Delete" button on the chatbot card
2. Confirm the deletion action
3. The chatbot is deactivated (not permanently deleted)
4. It no longer appears in the user interface
5. All content and settings are preserved

### Viewing Deleted Chatbots

1. Go to the "Deleted Chatbots" tab
2. See a list of all deactivated chatbots
3. Options to restore or permanently delete

### Restoring a Chatbot

1. In the "Deleted Chatbots" tab, find the chatbot to restore
2. Click "Restore"
3. The chatbot is reactivated and appears in the main list again
4. All previous content and settings are preserved

## Database Statistics

The "Database Statistics" tab provides system-wide information:

### Storage Usage

- Total database size
- Chat history size
- Chatbot contents size
- Percentage of maximum capacity used
- Visual progress bars showing storage distribution

### System Metrics

- Total messages stored
- Number of active chatbots
- Number of unique users
- Last updated timestamp

### Data Management

- Options for database maintenance
- Storage cleanup recommendations
- Monitoring database limits

## Best Practices

1. **Regular Content Updates**: Keep chatbot knowledge bases current
2. **Quota Management**: Set appropriate daily limits based on usage patterns
3. **Content Length**: Monitor character counts to balance comprehensiveness and cost
4. **Categorization**: Use consistent categories to organize chatbots
5. **Description Clarity**: Write clear, concise descriptions so users know which chatbot to use
6. **Testing After Changes**: Always test chatbots after editing content or settings
7. **Usage Analysis**: Regularly review conversation logs to identify improvement areas
8. **Storage Monitoring**: Keep an eye on database size to prevent reaching limits 