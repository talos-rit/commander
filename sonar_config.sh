#!/bin/sh

#load the .env file
if [ -f .env ]; then
    export $(grep -v '^#' .env | xargs)
else 
    echo ".env file not found!"
    exit 1
fi

#wait until sonarqube is up and running
echo "waiting for sonar qube to be up"
until curl -s -o /dev/null "$SONAR_HOST/api/system/status"; do
  echo "SonarQube is not reachable yet..."
  sleep 3
done

while [[ "$(curl -s "$SONAR_HOST/api/system/status" | grep -o '"status":"[^"]*"' | cut -d'"' -f4)" != "UP" ]]; do
  echo "SonarQube is starting..."
  sleep 5
done
echo "SonarQube is ready."

#does the default credentials still works?
if curl -s -u "$SONAR_DEFAULT_USER:$SONAR_DEFAULT_PASS" "$SONAR_HOST/api/authentication/validate" | grep -q '"valid":true'; then
  echo "changing the default credentials..."
  
  # Change password
  curl -s -X POST -u "$SONAR_DEFAULT_USER:$SONAR_DEFAULT_PASS" \
    "$SONAR_HOST/api/users/change_password" \
    -d "login=$SONAR_DEFAULT_USER&previousPassword=$SONAR_DEFAULT_PASS&password=$SONAR_NEW_PASS"


  
  echo "Password changed."
else
  echo "Default credentials doesnt work... nothing to do here.. continue..."
  exit 0
fi

echo "Generating token for user $SONAR_DEFAULT_USER..."
TOKEN_RESPONSE=$(curl -s -u "$SONAR_DEFAULT_USER:$SONAR_NEW_PASS" \
  -X POST "$SONAR_HOST/api/user_tokens/generate" \
  -d "name=$SONAR_TOKEN_NAME")

  TOKEN=$(echo "$TOKEN_RESPONSE" | grep -o '"token":"[^"]*"' | cut -d'"' -f4)

  #was the token ssuccessfully created?
if [ -n "$TOKEN" ]; then
    echo "Token generated successfully: $TOKEN"
    #does a old token exist in the file? if so then replace it
    if grep -q "^SONAR_TOKEN=" .env; then
        sed -i "s|^SONAR_TOKEN=.*|SONAR_TOKEN=$TOKEN|" .env
    else
        # append the token to the .env file if it doesnt exist
        echo "SONAR_TOKEN=$TOKEN" >> .env
    fi

else
    echo "Failed to generate token."
    exit 1
fi

# Check if coverage.xml and pytest_report.xml exist and are not empty
if [ -s coverage.xml ] && [ -s pytest_report.xml ]; then
    echo "Coverage and pytest report files are present and not empty."
else
    echo "Warning: Coverage and/or pytest report files are missing or empty. SonarQube analysis may be incomplete."
    # Optionally ask the user if they would like to run the tests to generate these files
    read -p "Would you like to run the tests to generate these files? (y/n) " answer
    if [ "$answer" = "y" ]; then
        echo "Running tests to generate coverage and pytest report files..."
        # Run the tests here (replace with your actual test command)
        uv run pytest --cov-report=xml:coverage.xml --junitxml=pytest_report.xml
    else
        echo "Skipping test execution. Please ensure coverage.xml and pytest_report.xml are generated before running SonarQube analysis or else the analysis may be incomplete."
    fi
fi

