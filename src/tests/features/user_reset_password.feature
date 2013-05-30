Feature: Resetting passwords

 Scenario: I try resetting the password for a non existing user
    Given I am on the login page
      And I click "Forgot password?"
     Then I should see "Enter your email address" within 3 seconds
     Then I fill in "email" with "non-existing@email.com"
      And I focus on "email" and hit the ENTER key
     Then I should see "No one with that email address was found" within 3 seconds


  Scenario: Andy Pham forgot his password, so he will recover it using the form
   Given a user named "Andy Pham" with email "andy-pham@mailinator.com" and password "123456"
     And I go to the login page
     And I click "Forgot password?"
    Then I should see "Enter your email address" within 3 seconds
    Then I fill in "email" with "andy-pham@mailinator.com"
     And I focus on "email" and hit the ENTER key
    Then I should see "Almost done!" within 3 seconds
     And I should see "Please check your email." within 3 seconds
     
     
  Scenario: Andy Pham checks mail and click on reset password link
   Given I wait for 10 seconds
     And I go to "http://andy-pham.mailinator.com/"
     And I should see "your password on jupo" within 5 seconds
    Then I click "your password on jupo"
     And I should see "To reset your password, please click this link:" within 5 seconds
    Then I click on "a[href*=reset_password]"
    Then I should see "Reset Password" within 3 seconds
    
  
  Scenario: New password is too short
    When I fill in "password" with "123"
     And I fill in "confirm" with "123"
     And I focus on "confirm" and hit the ENTER key
    Then I should see "Your password must be at least 6 characters long" within 3 seconds
    
  
  Scenario: Confirm password does not match
    When I fill in "password" with "123456"
     And I fill in "confirm" with "abc"
     And I focus on "confirm" and hit the ENTER key
    Then I should see "The two passwords you entered do not match" within 3 seconds
  
  
  Scenario: Andy Pham reset password successfully
    When I fill in "password" with "654321"
     And I fill in "confirm" with "654321"
     And I focus on "confirm" and hit the ENTER key
    Then I should see "Your password has been reset" within 3 seconds
    Then I fill in "password" with "654321"
     And I focus on "password" and hit the ENTER key
    Then I should see "News Feed" within 3 seconds
    Then I log out
    
    
  Scenario: Andy Pham tries to log in with old password
   Given I am on the login page
    Then I fill in "password" with "123456"
     And I focus on "password" and hit the ENTER key
    Then I should see "Incorrect password" within 3 seconds
    
    
  Scenario: Andy Pham tries to reset password with an invalid reset code
    When I go to "http://andy-pham.mailinator.com/"
     And I should see "your password on jupo" within 5 seconds
    Then I click "your password on jupo"
     And I should see "To reset your password, please click this link:" within 5 seconds
    Then I click on "a[href*=reset_password]"
    Then I should see "Reset Password" within 3 seconds
    
    Then I fill in "password" with "foobar"
     And I fill in "confirm" with "foobar"
     And I focus on "confirm" and hit the ENTER key
     
    Then I should see "Please provide a valid reset code" within 3 seconds
     
     
    
    
    
    
    
    
     
     