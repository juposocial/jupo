Feature: Logging In

  Scenario: Andy Pham successfully logs in
   Given a user named "Andy Pham" with email "andy@jupo.com" and password "123456"
    When I go to the home page
     And I click "Sign in"
     And I fill in "email" with "andy@jupo.com"
     And I fill in "password" with "123456"
     And I press ENTER key
    Then I should see "News Feed"
     And I should see "Andy Pham"
     
  Scenario: Andy Pham try to login with wrong password and username
    When I log out
     And I go to the sign in page
     And I fill in "email" with "andy@jupo.com"
     And I fill in "password" with "123"
     And I press ENTER key
    Then I should see "Invalid username or password"
    