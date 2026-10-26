// Copyright Unwritten Dao. All Rights Reserved.
// scaffold: editor target used only on a machine with UE5 installed.

using UnrealBuildTool;
using System.Collections.Generic;

public class UnwrittenDaoEditorTarget : TargetRules
{
	public UnwrittenDaoEditorTarget(TargetInfo Target) : base(Target)
	{
		Type = TargetType.Editor;
		DefaultBuildSettings = BuildSettingsVersion.V5;
		IncludeOrderVersion = EngineIncludeOrderVersion.Unreal5_5;
		ExtraModuleNames.Add("UnwrittenDao");
	}
}