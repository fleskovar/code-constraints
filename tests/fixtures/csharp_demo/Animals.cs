using System;

namespace Zoo.Animals
{
    /// <summary>
    /// Abstract base class for every living creature in the menagerie.
    /// </summary>
    public abstract class Animal
    {
        public string Name { get; set; }
        protected int Legs;

        public Animal(string name, int legs = 4)
        {
            Name = name;
            Legs = legs;
        }

        /// <summary>Return the sound this animal makes.</summary>
        public abstract string Speak();
    }

    public class Dog : Animal
    {
        public string Breed { get; set; }

        public Dog(string name) : base(name, 4)
        {
            Breed = "mixed";
        }

        public override string Speak()
        {
            // <uml-activity name="dog_speak" granularity="control-flow">
            if (Breed == "mixed")
            {
                return "Woof";
            }
            else
            {
                return "Bark";
            }
            // </uml-activity>
        }
    }
}
