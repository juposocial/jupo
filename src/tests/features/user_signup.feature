Feature: Signing up

  Scenario: Andy Pham successfully signs up
     When I go to the sign up page
      And I fill in "name" with "Andy Pham"
      And I fill in "email" with "andy@jupo.com"
      And I fill in "password" with "123456"
      And I focus on "password" and hit the ENTER key
     Then I should see "News Feed" within 3 seconds
      And I should see "Everyone" within 3 seconds
      
   
   Scenario: Andy Pham signs up with invalid email
      And I go to the sign up page
      And I fill in "name" with "Andy Pham"
      And I fill in "email" with "andy"
      And I fill in "password" with "123456"
      And I focus on "password" and hit the ENTER key
     Then I should see "Sign up" within 3 seconds
      And I should not see "News Feed"
      
      
   Scenario: Email already in use
     When I go to the sign up page
      And I fill in "name" with "Foobar"
      And I fill in "email" with "andy@jupo.com"
      And I fill in "password" with "123456"
      And I focus on "password" and hit the ENTER key
     Then I should see "andy@jupo.com" within 3 seconds
      And I should see "is already in use." within 3 seconds
      And I should not see "News Feed"
      
      
   Scenario: Andy Pham signs up with invalid password
     When I go to the sign up page
      And I fill in "name" with "Andy Pham"
      And I fill in "email" with "andy_@jupo.com"
      And I fill in "password" with "123"
      And I focus on "password" and hit the ENTER key
     Then I should see "Your password must be at least 6 characters long." within 3 seconds
      And I should not see "News Feed"
      
   
      
    