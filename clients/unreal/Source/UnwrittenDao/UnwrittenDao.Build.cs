// Copyright Unwritten Dao. All Rights Reserved.

using UnrealBuildTool;

public class UnwrittenDao : ModuleRules
{
	public UnwrittenDao(ReadOnlyTargetRules Target) : base(Target)
	{
		PCHUsage = PCHUsageMode.UseExplicitOrSharedPCHs;

		PublicDependencyModuleNames.AddRange(new string[]
		{
			"Core",
			"CoreUObject",
			"Engine",
			"InputCore",
			"HTTP",
			"Json",
			"JsonUtilities",
			"UMG",
			"Slate",
			"SlateCore",
			"AIModule",
			"NavigationSystem"
		});

		PrivateDependencyModuleNames.AddRange(new string[] { });
	}
}