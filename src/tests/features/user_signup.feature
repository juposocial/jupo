Feature: Signing up

  Scenario: Andy Pham successfully signs up
     When I go to the sign up page
      And I fill in "name" with "Andy Pham"
      And I fill in "email" with "andy@jupo.com"
      And I fill in "password" with "123456"
      And I press ENTER key
      And I should see "News Feed"
      And I should see "Everyone"
      
   
   Scenario: Andy Pham signs up with invalid email
      And I go to the sign up page
      And I fill in "name" with "Andy Pham"
      And I fill in "email" with "andy"
      And I fill in "password" with "123456"
      And I press ENTER key
      And I should not see "News Feed"
      
      
   Scenario: Email already in use
     When I go to the sign up page
      And I fill in "name" with "Foobar"
      And I fill in "email" with "andy@jupo.com"
      And I fill in "password" with "123456"
      And I press ENTER key
     Then I should see "andy@jupo.com" 
      And I should see "is already in use."
      And I should not see "News Feed"
      
      
   Scenario: Andy Pham signs up with invalid password
     When I go to the sign up page
      And I fill in "name" with "Andy Pham"
      And I fill in "email" with "andy_@jupo.com"
      And I fill in "password" with "123"
      And I press ENTER key
     Then I should see "Your password must be at least 6 characters long."
      And I should not see "News Feed"
      
   
      
    