function myFunction() {
    var doc = DocumentApp.openById('~'); //replace with ID
    var footnotes = doc.getFootnotes();

    // Fill in mapping here:
    var mapping = {
      'http://hameedmarine.com/services.html': 'https://web.archive.org/http://hameedmarine.com/services.html',
    }

    for (var i = 0; i < footnotes.length; i++) {
      var contents = footnotes[i].getFootnoteContents();
      for (var j = 0; j < contents.getNumChildren(); j++) {
        var child = contents.getChild(j);
        var text = child.editAsText();
        if (text) {
          var fullText = text.getText(); // Original text
          var startIndex = 0;
  
          // Iterate over characters in the original text
          while (startIndex < fullText.length) {
            var url = text.getLinkUrl(startIndex);
  
            if (url) {
              // Find the full range of the phrase with the URL
              var phraseStart = startIndex;
              var phraseEnd = startIndex;
  
              while (phraseEnd < fullText.length && text.getLinkUrl(phraseEnd) === url) {
                phraseEnd++;
              }
  
              phraseEnd--; // Adjust to the last character of the URL phrase
  
              // Extract the full phrase
              var phrase = fullText.substring(phraseStart, phraseEnd + 1).trim();
  
              // Skip if the phrase starts with "(Archived"
              if (phrase.toLowerCase().startsWith("(archived") || phrase.toLowerCase().startsWith("archived")) {
                Logger.log("Skipping phrase: " + phrase);
                startIndex = phraseEnd + 1;
                continue;
              }
  
              Logger.log("Found phrase: " + phrase + " with link: " + url);
  
              // Append a single space and "(Archived)" to the phrase
              var appendText = " (Archived)";
              text.insertText(phraseEnd + 1, appendText);
  
              let mark = false
              if (url in mapping) {
                mark = true
                replaceUrl = mapping[url]
              }
  
              // Apply the new URL only to "(Archived)"
              var startArchived = phraseEnd + 2; // Start after the space
              var endArchived = startArchived + appendText.length - 2; // Exclude the initial space
  
              // Apply green highlight to "(Archived)"
              if (mark) {
                text.setLinkUrl(startArchived, endArchived, replaceUrl);
                text.setBackgroundColor(startArchived, endArchived, "#00FF00");
              } else {
                text.setBackgroundColor(startArchived, endArchived, "#FF0000");
              }
  
              // Recalculate fullText to reflect the added text
              fullText = text.getText();
  
              // Move startIndex past the newly appended "(Archived)"
              startIndex = endArchived + 1;
            } else {
              startIndex++; // Move to the next character if no URL is found
            }
          }
        }
      }
    }
  }
  