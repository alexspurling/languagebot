var topic = undefined;
var english = undefined;
var language = undefined;

function addBotText(text) {
    const chatDiv = document.getElementById("chat");
    chatDiv.innerHTML += "<div class=\"bot\">" + text.replace(/\n/g, "<br>") + "</div>"
    chatDiv.scrollTop = chatDiv.scrollHeight; // Scroll to the bottom
}

function addHumanText(text) {
    const chatDiv = document.getElementById("chat");
    chatDiv.innerHTML += "<div class=\"human\">" + text.replace(/\n/g, "<br>") + "</div>"
    chatDiv.scrollTop = chatDiv.scrollHeight; // Scroll to the bottom
}

// Function to send the POST request with the content of the text field
function getSentence(topic) {
    const textField = document.getElementById("textfield")
    const statusField = document.getElementById('status');

    // Get the CSRF token from the meta tag
    const csrftoken = document.querySelector('meta[name="csrf-token"]').getAttribute('content');

    // Make a POST request
    fetch('/getsentence', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'X-CSRFToken': csrftoken,
        },
        body: JSON.stringify({ language: language, topic: topic }),
    })
    .then(response => {
        if (response.ok) {
            statusField.innerHTML = '<p>POST request was successful. Response status: ' + response.status + '</p>';
        } else {
            statusField.innerHTML = '<p>POST request failed. Response status: ' + response.status + '</p>';
        }
        return response.json();
    })
    .then(data => {
        console.log('Server response:', data);
        english = data.english;
        addBotText("Translate the following:\n" + data.english)
        textField.value = "";
    })
    .catch(error => {
        console.error('Error during POST request:', error);
        statusField.innerHTML = '<p>Error during POST request: ' + error + '</p>';
    });
}

function getFormattedString(matches, str) {
    var formattedString = "";
    var lastIdx = 0;
    for (var i = 0; i < matches.length; i++) {
        console.log("match", matches[i]);
        var match = matches[i];
        formattedString += str.substring(lastIdx, match[1]); // Include everything up until this latest match
        // If this word was found in the other string, then set the class to "correct", otherwise mark it as "incorrect"
        var c = match[2] >= 0 ? "c" : "i";
        formattedString += "<span class=\"" + c + "\">"
        formattedString += str.substring(match[1], match[1] + match[0].length)
        formattedString += "</span>"
        lastIdx = match[1] + match[0].length;
    }
    formattedString += str.substring(lastIdx); // Include everything after the final match
    return formattedString;
}

// Function to send the POST request with the content of the text field
function submitSentence(entry) {
    const statusField = document.getElementById('status');

    // Get the CSRF token from the meta tag
    const csrftoken = document.querySelector('meta[name="csrf-token"]').getAttribute('content');

    // Make a POST request
    fetch('/submitsentence', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'X-CSRFToken': csrftoken,
        },
        body: JSON.stringify({ language: language, english: english, submission: entry }),
    })
    .then(response => {
        if (response.ok) {
            statusField.innerHTML = '<p>POST request was successful. Response status: ' + response.status + '</p>';
        } else {
            statusField.innerHTML = '<p>POST request failed. Response status: ' + response.status + '</p>';
        }
        return response.json();
    })
    .then(data => {
        console.log('Server response:', data);

        if (data.correct) {
            addHumanText(entry);
            addBotText("<span class=\"c\">Correct!</span>")
            getSentence(topic); // Get the next sentence for the topic
        } else {
            var formattedEntry = getFormattedString(data.entered_word_matches, entry)
            addHumanText(formattedEntry);
            addBotText("Incorrect. The correct translation is: <br>" + data.translation)
            getSentence(topic); // Get the next sentence for the topic
        }
    })
    .catch(error => {
        console.error('Error during POST request:', error);
        statusField.innerHTML = '<p>Error during POST request: ' + error + '</p>';
    });
}

document.addEventListener('DOMContentLoaded', function() {
    // Find the text field and the log container
    const instructionsField = document.getElementById('instructions');
    const textField = document.getElementById("textfield")
    const statusField = document.getElementById('status');

    // Add an event listener to trigger the POST request
    textField.addEventListener('keydown', function(event) {
        if (event.key === 'Enter') {
            if (textField.value) {
                if (!language) {
                    language = textField.value.toLowerCase();
                    addHumanText(textField.value)
                    textField.value = "";
                    addBotText("Great, let's learn " + language + "! Now please choose a topic to learn about.")
                } else if (!topic) {
                    topic = textField.value;
                    addHumanText(textField.value)
                    textField.value = "";
                    addBotText("Ok, let's learn about " + topic + "...")
                    getSentence(topic);
                } else {
                    entry = textField.value;
                    submitSentence(entry);
                }
            }
        }
    });

    // Default to hobbies for now
//    topic = "hobbies";
//    getSentence(topic);
});