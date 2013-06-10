Feature: Create Note

  Scenario: Andy Pham successfully logs in
   Given a user named "Andy Pham" with email "andy@jupo.com" and password "123456"
    When I go to the home page
     And I click "Sign in"
     And I fill in "email" with "andy@jupo.com"
     And I fill in "password" with "123456"
     And I focus on "password" and hit the ENTER key
    Then I should see "News Feed" within 5 seconds
     And I should see "Andy Pham" within 5 seconds
     
  Scenario: Andy Pham create note
    When I go to the notes page
      And I click "+ Create a new note"
    Then I should see "Heading" within 3 seconds
    Then I should see "Normal text" within 3 seconds