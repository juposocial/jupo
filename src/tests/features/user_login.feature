Feature: Logging In

  Scenario: Andy Pham successfully logs in
   Given a user named "Andy Pham" with email "andy@jupo.com" and password "123456"
    When I go to the home page
     And I click "Sign in"
     And I fill in "email" with "andy@jupo.com"
     And I fill in "password" with "123456"
     And I focus on "password" and hit the ENTER key
    Then I should see "News Feed" within 3 seconds
     And I should see "Andy Pham" within 3 seconds
     
  Scenario: Andy Pham try to login with wrong password
    When I log out
     And I go to the sign in page
    Then I fill in "email" with "andy@jupo.com"
     And I fill in "password" with "123"
     And I focus on "password" and hit the ENTER key
    Then I should see "Incorrect password" within 3 seconds
     And I should see "Reset password" within 3 seconds
     
  Scenario: Andy Pham try to login with unexisted email
    When I go to the sign in page
     And I fill in "email" with "andy123123@jupo.com"
     And I fill in "password" with "123"
     And I focus on "password" and hit the ENTER key
    Then I should see "No account found" within 3 seconds
     And I should see "Sign up for Jupo" within 3 seconds
    